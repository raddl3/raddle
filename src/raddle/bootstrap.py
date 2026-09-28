"""Deterministic bootstrap means over a shared, chunked resampling plan."""

import math
import statistics
import time
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from functools import lru_cache, partial
from typing import Any, cast

import numpy as np
from numpy.typing import ArrayLike, NDArray

from raddle import cupy_backend
from raddle.contracts import (
    AcceleratorDescriptor,
    BenchmarkReceipt,
    BootstrapCaseDescriptor,
    ExecutionProvenance,
    GPUProvenance,
    ImplementationIdentity,
    Synchronization,
    TimingScope,
    TransferInclusion,
    ValidationPolicy,
    ValidationReceipt,
)

FloatArray = NDArray[np.float64]
IndexArray = NDArray[np.int64]
CHUNK_INDICES = 1_048_576
ALGORITHM = "splitmix64.counter_reject.v1"
NUMPY = ImplementationIdentity("numpy.vectorized", "1")
CUPY = ImplementationIdentity("cupy.vectorized", "2", "cuda12")
POLICY = ValidationPolicy("float64.bootstrap_distribution.v1", 1e-12, 1e-12)
DESCRIPTOR = AcceleratorDescriptor(
    id="stats.bootstrap",
    version="0.1.0",
    name="Bootstrap resampling",
    reference=ImplementationIdentity("python.scalar", "1"),
    candidates=(NUMPY, CUPY),
    input_contract=(
        "Finite nonempty float64 1-D sample; positive resamples, uint64 seed, "
        "confidence level in (0, 1); arithmetic mean only"
    ),
    output_contract=(
        "Original mean, float64 bootstrap means, sample standard error (ddof=1), "
        "linear percentile confidence interval"
    ),
    precision="float64",
    supported_environment="CPython >=3.12, NumPy >=2,<3; optional CUDA 12 on Linux",
    validation_policy=POLICY,
    cases=(
        BootstrapCaseDescriptor("bootstrap.small", 3, 20, 7, 0.8),
        BootstrapCaseDescriptor("bootstrap.256", 256, 256, 11, 0.95),
        BootstrapCaseDescriptor("bootstrap.1k", 256, 1024, 11, 0.95),
        BootstrapCaseDescriptor("bootstrap.standard", 256, 4096, 11, 0.95),
        BootstrapCaseDescriptor("bootstrap.16k", 256, 16384, 11, 0.95),
        BootstrapCaseDescriptor("bootstrap.64k", 256, 65536, 11, 0.95),
    ),
    algorithm=ALGORITHM,
)


@dataclass(frozen=True)
class BootstrapInput:
    sample: ArrayLike
    resamples: int
    seed: int
    confidence_level: float

    def __post_init__(self) -> None:
        try:
            sample = np.array(self.sample, dtype=np.float64, copy=True)
        except (TypeError, ValueError) as error:
            raise ValueError("sample must contain float64 values") from error
        if sample.ndim != 1 or sample.size == 0 or not np.isfinite(sample).all():
            raise ValueError("sample must be a finite nonempty 1-D array")
        if type(self.resamples) is not int or self.resamples < 2:
            raise ValueError("resamples must be an integer >= 2")
        if type(self.seed) is not int or not 0 <= self.seed < 2**64:
            raise ValueError("seed must be a uint64 integer")
        if (
            not math.isfinite(self.confidence_level)
            or not 0 < self.confidence_level < 1
        ):
            raise ValueError("confidence_level must be finite and in (0, 1)")
        if sample.size > CHUNK_INDICES or sample.size * self.resamples >= 2**64:
            raise ValueError("bootstrap plan exceeds v0.1 size limit")
        sample.flags.writeable = False
        object.__setattr__(self, "sample", sample)


@dataclass(frozen=True)
class BootstrapResult:
    original_statistic: float
    distribution: FloatArray
    standard_error: float
    confidence_level: float
    percentile_interval: tuple[float, float]


def case(case_id: str) -> BootstrapInput:
    definition = next((item for item in DESCRIPTOR.cases if item.id == case_id), None)
    if not isinstance(definition, BootstrapCaseDescriptor):
        raise KeyError(case_id)
    return BootstrapInput(
        np.linspace(0.0, 1.0, definition.sample_size, dtype=np.float64),
        definition.resamples,
        definition.seed,
        definition.confidence_level,
    )


def _mix64(values: NDArray[np.uint64]) -> NDArray[np.uint64]:
    """SplitMix64's fixed uint64 mixing steps, with defined wraparound."""
    with np.errstate(over="ignore"):
        values ^= values >> np.uint64(30)
        values *= np.uint64(0xBF58476D1CE4E5B9)
        values ^= values >> np.uint64(27)
        values *= np.uint64(0x94D049BB133111EB)
        values ^= values >> np.uint64(31)
    return values


def plans(inputs: BootstrapInput) -> Iterator[IndexArray]:
    """Counter-addressed draws are identical regardless of chunk boundaries."""
    size = cast(FloatArray, inputs.sample).size
    rows_per_chunk = max(1, CHUNK_INDICES // size)
    rejection_limit = (1 << 64) % size
    for start in range(0, inputs.resamples, rows_per_chunk):
        rows = min(rows_per_chunk, inputs.resamples - start)
        draws = np.arange(start * size, (start + rows) * size, dtype=np.uint64)
        with np.errstate(over="ignore"):
            draws += np.uint64(inputs.seed)
            draws += np.uint64(0x9E3779B97F4A7C15)
        _mix64(draws)
        # Reject values that would bias modulo for a non-power-of-two size.
        while rejection_limit and np.any(draws < rejection_limit):
            rejected = draws < rejection_limit
            retry = draws[rejected].copy()
            # Zero is SplitMix64's fixed point; restart it before re-mixing.
            retry[retry == 0] = np.uint64(0x9E3779B97F4A7C15)
            draws[rejected] = _mix64(retry)
        np.remainder(draws, np.uint64(size), out=draws)
        yield draws.view(np.int64).reshape(rows, size)


def _result(inputs: BootstrapInput, distribution: FloatArray) -> BootstrapResult:
    sample = cast(FloatArray, inputs.sample)
    if distribution.shape != (inputs.resamples,) or not np.isfinite(distribution).all():
        raise ValueError("bootstrap distribution must be finite and complete")
    alpha = (1 - inputs.confidence_level) * 50
    bounds = np.percentile(distribution, (alpha, 100 - alpha), method="linear")
    distribution.flags.writeable = False
    result = BootstrapResult(
        float(np.mean(sample)),
        distribution,
        float(np.std(distribution, ddof=1)),
        inputs.confidence_level,
        (float(bounds[0]), float(bounds[1])),
    )
    if not all(
        math.isfinite(value)
        for value in (
            result.original_statistic,
            result.standard_error,
            *result.percentile_interval,
        )
    ):
        raise ValueError("bootstrap summary must be finite")
    return result


def _scalar_distribution(
    sample: FloatArray, chunks: Iterator[IndexArray]
) -> FloatArray:
    return np.fromiter(
        (
            sum(float(sample[index]) for index in row) / sample.size
            for chunk in chunks
            for row in chunk
        ),
        dtype=np.float64,
    )


def _numpy_distribution(sample: FloatArray, chunks: Iterator[IndexArray]) -> FloatArray:
    return np.concatenate([np.mean(sample[chunk], axis=1) for chunk in chunks])


def reference(inputs: BootstrapInput) -> BootstrapResult:
    return _result(
        inputs, _scalar_distribution(cast(FloatArray, inputs.sample), plans(inputs))
    )


def accelerated(inputs: BootstrapInput) -> BootstrapResult:
    return _result(
        inputs, _numpy_distribution(cast(FloatArray, inputs.sample), plans(inputs))
    )


def _gpu_distribution(
    inputs: BootstrapInput,
    cupy: Any,
    device_sample: Any | None = None,
) -> Any:
    if device_sample is None:
        device_sample = cupy.asarray(inputs.sample, dtype=cupy.float64)
    size = cast(FloatArray, inputs.sample).size
    output = cupy.empty(inputs.resamples, dtype=cupy.float64)
    rows_per_chunk = max(1, CHUNK_INDICES // size)
    kernel = _bootstrap_kernel(cupy)
    for start in range(0, inputs.resamples, rows_per_chunk):
        rows = min(rows_per_chunk, inputs.resamples - start)
        kernel(
            (rows,),
            (256,),
            (
                device_sample,
                output,
                np.uint64(inputs.seed),
                np.uint64(size),
                np.uint64((1 << 64) % size),
                np.uint64(start),
            ),
        )
    return output


@lru_cache(maxsize=1)
def _bootstrap_kernel(cupy: Any) -> Any:
    return cupy.RawKernel(
        r"""
extern "C" __device__ unsigned long long mix64(unsigned long long x) {
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
    return x ^ (x >> 31);
}
extern "C" __global__ void bootstrap_mean(
    const double* sample, double* result, unsigned long long seed,
    unsigned long long size, unsigned long long limit,
    unsigned long long start
) {
    __shared__ double sums[256];
    unsigned int tid = threadIdx.x;
    unsigned long long row = start + blockIdx.x;
    double total = 0.0;
    for (unsigned long long i = tid; i < size; i += blockDim.x) {
        unsigned long long draw = mix64(row * size + i + seed + 0x9E3779B97F4A7C15ULL);
        while (draw < limit) draw = mix64(draw == 0 ? 0x9E3779B97F4A7C15ULL : draw);
        unsigned long long index = (size & (size - 1)) == 0
            ? draw & (size - 1) : draw % size;
        total += sample[index];
    }
    sums[tid] = total;
    __syncthreads();
    for (unsigned int offset = blockDim.x / 2; offset > 0; offset >>= 1) {
        if (tid < offset) sums[tid] += sums[tid + offset];
        __syncthreads();
    }
    if (tid == 0) result[row] = sums[0] / size;
}
""",
        "bootstrap_mean",
    )


def _gpu_mix64(values: Any, cupy: Any) -> Any:
    values = (values ^ (values >> cupy.uint64(30))) * cupy.uint64(0xBF58476D1CE4E5B9)
    values = (values ^ (values >> cupy.uint64(27))) * cupy.uint64(0x94D049BB133111EB)
    return values ^ (values >> cupy.uint64(31))


def _gpu_reject(draws: Any, size: int, cupy: Any) -> Any:
    limit = (1 << 64) % size
    while limit and bool(cupy.any(draws < limit)):
        rejected = draws < limit
        retry = draws[rejected]
        retry = cupy.where(retry == 0, cupy.uint64(0x9E3779B97F4A7C15), retry)
        draws[rejected] = _gpu_mix64(retry, cupy)
    return draws


def device_plans_for(inputs: BootstrapInput, cupy: Any) -> Iterator[Any]:
    """Generate the reference row-major counter stream directly on device."""
    size = cast(FloatArray, inputs.sample).size
    rows_per_chunk = max(1, CHUNK_INDICES // size)
    for start in range(0, inputs.resamples, rows_per_chunk):
        rows = min(rows_per_chunk, inputs.resamples - start)
        counters = cupy.arange(start * size, (start + rows) * size, dtype=cupy.uint64)
        draws = _gpu_mix64(
            counters + cupy.uint64(inputs.seed) + cupy.uint64(0x9E3779B97F4A7C15),
            cupy,
        )
        yield (
            (_gpu_reject(draws, size, cupy) % cupy.uint64(size))
            .astype(cupy.int64)
            .reshape(rows, size)
        )


def gpu_accelerated(inputs: BootstrapInput, cupy: Any | None = None) -> BootstrapResult:
    cupy = cupy_backend.load() if cupy is None else cupy
    distribution = cast(FloatArray, cupy.asnumpy(_gpu_distribution(inputs, cupy)))
    return _result(inputs, distribution)


def availability(implementation_id: str) -> tuple[bool, str]:
    if implementation_id in (DESCRIPTOR.reference.id, NUMPY.id):
        return True, "available in the base package"
    if implementation_id == CUPY.id:
        return cupy_backend.availability()
    raise KeyError(implementation_id)


def _candidate(
    inputs: BootstrapInput, implementation_id: str
) -> tuple[BootstrapResult, GPUProvenance | None]:
    if implementation_id == NUMPY.id:
        return accelerated(inputs), None
    if implementation_id == CUPY.id:
        cupy = cupy_backend.load()
        return gpu_accelerated(inputs, cupy), cupy_backend.provenance(cupy)
    raise KeyError(implementation_id)


def validate(
    case_id: str,
    expected: BootstrapResult,
    actual: BootstrapResult,
    candidate: ImplementationIdentity = NUMPY,
    gpu: GPUProvenance | None = None,
) -> ValidationReceipt:
    values = np.array(
        [
            expected.original_statistic,
            expected.standard_error,
            *expected.percentile_interval,
            *expected.distribution,
        ],
        dtype=np.float64,
    )
    compared = np.array(
        [
            actual.original_statistic,
            actual.standard_error,
            *actual.percentile_interval,
            *actual.distribution,
        ],
        dtype=np.float64,
    )
    if (
        values.shape != compared.shape
        or not np.isfinite(compared).all()
        or actual.confidence_level != expected.confidence_level
    ):
        raise ValueError(
            "candidate output must be finite and match shape and confidence"
        )
    difference = np.abs(compared - values)
    threshold = POLICY.absolute_tolerance + POLICY.relative_tolerance * np.abs(values)
    relative_region = (
        np.abs(values) >= POLICY.absolute_tolerance / POLICY.relative_tolerance
    )
    relative_error = (
        float(np.max(difference[relative_region] / np.abs(values[relative_region])))
        if np.any(relative_region)
        else 0.0
    )
    return ValidationReceipt(
        schema_version=2,
        accelerator_id=DESCRIPTOR.id,
        accelerator_version=DESCRIPTOR.version,
        case_id=case_id,
        reference=DESCRIPTOR.reference,
        candidate=candidate,
        precision="float64",
        policy=POLICY,
        status="matched" if np.all(difference <= threshold) else "mismatched",
        compared_values=int(values.size),
        max_absolute_error=float(np.max(difference)),
        max_relative_error=relative_error,
        provenance=ExecutionProvenance.current(gpu),
    )


def verify(case_id: str, implementation_id: str = NUMPY.id) -> ValidationReceipt:
    inputs = case(case_id)
    actual, gpu = _candidate(inputs, implementation_id)
    candidate = next(
        item for item in DESCRIPTOR.candidates if item.id == implementation_id
    )
    return validate(case_id, reference(inputs), actual, candidate, gpu)


def _timed(action: Callable[[], object], synchronize: Callable[[], None]) -> int:
    synchronize()
    start = time.perf_counter_ns()
    result = action()
    synchronize()
    duration = time.perf_counter_ns() - start
    del result
    return duration


def _no_sync() -> None:
    return None


def benchmark(
    case_id: str,
    repeat: int,
    warmup: int = 1,
    implementation_id: str = NUMPY.id,
    timing_scope: TimingScope = TimingScope.END_TO_END,
    baseline_id: str = "python.scalar",
) -> BenchmarkReceipt:
    if type(repeat) is not int or repeat <= 0 or type(warmup) is not int or warmup < 0:
        raise ValueError("repeat must be positive and warmup nonnegative")
    if baseline_id not in (DESCRIPTOR.reference.id, NUMPY.id):
        raise KeyError(baseline_id)
    inputs = case(case_id)
    actual, gpu = _candidate(inputs, implementation_id)
    candidate = next(
        item for item in DESCRIPTOR.candidates if item.id == implementation_id
    )
    validation = validate(case_id, reference(inputs), actual, candidate, gpu)
    if validation.status != "matched":
        raise ValueError("benchmark validation failed")
    baseline = DESCRIPTOR.reference if baseline_id == DESCRIPTOR.reference.id else NUMPY
    baseline_action: Callable[[], object] = partial(
        reference if baseline_id == DESCRIPTOR.reference.id else accelerated, inputs
    )
    candidate_action: Callable[[], object]
    synchronize: Callable[[], None] = _no_sync
    transfers = TransferInclusion.NOT_APPLICABLE
    candidate_synchronization = Synchronization.SYNCHRONOUS
    if timing_scope == TimingScope.COMPUTE_ONLY:
        host_plans = list(plans(inputs))
        distribution = (
            _scalar_distribution
            if baseline_id == DESCRIPTOR.reference.id
            else _numpy_distribution
        )

        # Re-create the iterator for each repetition.
        def run_baseline() -> FloatArray:
            return distribution(cast(FloatArray, inputs.sample), iter(host_plans))

        baseline_action = run_baseline
    if implementation_id == CUPY.id:
        cupy = cupy_backend.load()
        synchronize = cupy.cuda.get_current_stream().synchronize
        if timing_scope == TimingScope.COMPUTE_ONLY:
            device_sample = cupy.asarray(inputs.sample, dtype=cupy.float64)
            synchronize()
            candidate_action = partial(_gpu_distribution, inputs, cupy, device_sample)
            transfers = TransferInclusion.EXCLUDED
        else:
            candidate_action = partial(gpu_accelerated, inputs, cupy)
            transfers = TransferInclusion.INCLUDED
        candidate_synchronization = Synchronization.CUDA_STREAM
    else:
        if timing_scope == TimingScope.COMPUTE_ONLY:

            def run_numpy() -> FloatArray:
                return _numpy_distribution(
                    cast(FloatArray, inputs.sample), iter(host_plans)
                )

            candidate_action = run_numpy
        else:
            candidate_action = partial(accelerated, inputs)
    for _ in range(warmup):
        baseline_action()
        candidate_action()
        synchronize()
    baseline_times = tuple(_timed(baseline_action, _no_sync) for _ in range(repeat))
    candidate_times = tuple(
        _timed(candidate_action, synchronize) for _ in range(repeat)
    )
    median_baseline = statistics.median(baseline_times)
    median_candidate = statistics.median(candidate_times)
    return BenchmarkReceipt(
        schema_version=3,
        accelerator_id=DESCRIPTOR.id,
        accelerator_version=DESCRIPTOR.version,
        case_id=case_id,
        workload=asdict(next(item for item in DESCRIPTOR.cases if item.id == case_id)),
        validation=validation,
        clock="perf_counter_ns",
        timing_scope=timing_scope,
        setup_included=False,
        host_device_transfers=transfers,
        baseline=baseline,
        baseline_synchronization=Synchronization.SYNCHRONOUS,
        candidate_synchronization=candidate_synchronization,
        warmup=warmup,
        repeat=repeat,
        baseline_times_ns=baseline_times,
        candidate_times_ns=candidate_times,
        median_baseline_ns=median_baseline,
        median_candidate_ns=median_candidate,
        speedup=median_baseline / median_candidate,
        provenance=ExecutionProvenance.current(gpu),
    )
