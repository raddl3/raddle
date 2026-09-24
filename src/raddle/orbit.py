"""Batched point-mass two-body propagation with independent RK4 paths."""

import math
import statistics
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from functools import partial

import numpy as np
from numpy.typing import ArrayLike, NDArray

from raddle import cupy_backend
from raddle.contracts import (
    AcceleratorDescriptor,
    BenchmarkReceipt,
    CaseDescriptor,
    ExecutionProvenance,
    GPUProvenance,
    ImplementationIdentity,
    Synchronization,
    TimingScope,
    TransferInclusion,
    ValidationPolicy,
    ValidationReceipt,
)

StateBatch = NDArray[np.float64]


@dataclass(frozen=True)
class PropagationInput:
    initial_states: ArrayLike
    mu: float
    dt: float
    steps: int

    def __post_init__(self) -> None:
        try:
            states = np.array(self.initial_states, dtype=np.float64, copy=True)
        except (TypeError, ValueError) as error:
            raise ValueError("initial_states must contain float64 values") from error
        if states.ndim != 2 or states.shape[0] < 1 or states.shape[1] != 6:
            raise ValueError("initial_states must have shape (batch >= 1, 6)")
        if not np.isfinite(states).all():
            raise ValueError("initial_states must be finite")
        if np.any(np.linalg.norm(states[:, :3], axis=1) == 0):
            raise ValueError("initial_states must have nonzero radius")
        if not math.isfinite(self.mu) or self.mu <= 0:
            raise ValueError("mu must be finite and positive")
        if not math.isfinite(self.dt) or self.dt <= 0:
            raise ValueError("dt must be finite and positive")
        if type(self.steps) is not int or self.steps <= 0:
            raise ValueError("steps must be a positive integer")
        states.flags.writeable = False
        object.__setattr__(self, "initial_states", states)


POLICY = ValidationPolicy(
    id="float64.state_elementwise.v1",
    absolute_tolerance=1e-11,
    relative_tolerance=1e-10,
)
NUMPY = ImplementationIdentity("numpy.vectorized", "1")
CUPY = ImplementationIdentity("cupy.vectorized", "1", "cuda12")
DESCRIPTOR = AcceleratorDescriptor(
    id="orbit.two_body_rk4",
    version="0.2.0",
    name="Batched two-body propagation",
    reference=ImplementationIdentity("python.scalar", "1"),
    candidates=(NUMPY, CUPY),
    input_contract=(
        "Finite float64 (batch >= 1, 6) Cartesian states; "
        "positive mu, dt, steps in consistent units"
    ),
    output_contract=(
        "Finite float64 (batch, 6) final Cartesian states after exactly steps RK4 steps"
    ),
    precision="float64",
    supported_environment="CPython >=3.12, NumPy >=2,<3; optional CUDA 12 on Linux",
    validation_policy=POLICY,
    cases=(
        CaseDescriptor("circular.small", 4, 1.0, math.tau / 256, 256),
        CaseDescriptor("batch.standard", 256, 1.0, 0.01, 128),
        CaseDescriptor("batch.1k", 1024, 1.0, 0.01, 128),
        CaseDescriptor("batch.4k", 4096, 1.0, 0.01, 128),
        CaseDescriptor("batch.16k", 16384, 1.0, 0.01, 128),
        CaseDescriptor("batch.64k", 65536, 1.0, 0.01, 128),
    ),
)


def case(case_id: str) -> PropagationInput:
    definition = next((item for item in DESCRIPTOR.cases if item.id == case_id), None)
    if not isinstance(definition, CaseDescriptor):
        raise KeyError(case_id)
    states = np.empty((definition.trajectories, 6), dtype=np.float64)
    for index in range(definition.trajectories):
        phase = math.tau * index / definition.trajectories
        radius = 1.0 + 0.1 * (index % 7)
        speed = math.sqrt(definition.mu / radius)
        states[index] = (
            radius * math.cos(phase),
            radius * math.sin(phase),
            0.0,
            -speed * math.sin(phase),
            speed * math.cos(phase),
            0.0,
        )
    return PropagationInput(states, definition.mu, definition.dt, definition.steps)


def reference(inputs: PropagationInput) -> StateBatch:
    """Legible scalar RK4, one trajectory at a time."""

    def derivative(state: list[float]) -> list[float]:
        x, y, z, vx, vy, vz = state
        radius = math.sqrt(x * x + y * y + z * z)
        if radius == 0 or not math.isfinite(radius):
            raise ValueError("integration reached singular or non-finite radius")
        scale = -inputs.mu / (radius * radius * radius)
        return [vx, vy, vz, scale * x, scale * y, scale * z]

    result: list[list[float]] = []
    for row in np.asarray(inputs.initial_states):
        state = [float(value) for value in row]
        for _ in range(inputs.steps):
            k1 = derivative(state)
            k2 = derivative(
                [
                    value + inputs.dt * slope / 2
                    for value, slope in zip(state, k1, strict=True)
                ]
            )
            k3 = derivative(
                [
                    value + inputs.dt * slope / 2
                    for value, slope in zip(state, k2, strict=True)
                ]
            )
            k4 = derivative(
                [
                    value + inputs.dt * slope
                    for value, slope in zip(state, k3, strict=True)
                ]
            )
            state = [
                value + inputs.dt * (a + 2 * b + 2 * c + d) / 6
                for value, a, b, c, d in zip(state, k1, k2, k3, k4, strict=True)
            ]
            if not all(map(math.isfinite, state)):
                raise ValueError("integration produced a non-finite state")
        result.append(state)
    return np.asarray(result, dtype=np.float64)


def accelerated(inputs: PropagationInput) -> StateBatch:
    """The same RK4 stages, vectorized across independent trajectories."""

    def derivative(states: StateBatch) -> StateBatch:
        position = states[:, :3]
        radius_squared = np.sum(position * position, axis=1)
        if np.any(radius_squared == 0) or not np.isfinite(radius_squared).all():
            raise ValueError("integration reached singular or non-finite radius")
        scale = -inputs.mu / (radius_squared * np.sqrt(radius_squared))
        return np.concatenate((states[:, 3:], position * scale[:, None]), axis=1)

    states = np.array(inputs.initial_states, dtype=np.float64, copy=True)
    for _ in range(inputs.steps):
        k1 = derivative(states)
        k2 = derivative(states + inputs.dt * k1 / 2)
        k3 = derivative(states + inputs.dt * k2 / 2)
        k4 = derivative(states + inputs.dt * k3)
        states += inputs.dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6
        if not np.isfinite(states).all():
            raise ValueError("integration produced a non-finite state")
    return states


def validate(
    case_id: str,
    expected: StateBatch,
    actual: StateBatch,
    candidate: ImplementationIdentity = NUMPY,
    gpu: GPUProvenance | None = None,
) -> ValidationReceipt:
    if expected.shape != actual.shape or not np.isfinite(actual).all():
        raise ValueError("candidate output must be finite and match reference shape")
    difference = np.abs(expected - actual)
    threshold = POLICY.absolute_tolerance + POLICY.relative_tolerance * np.abs(expected)
    relative_region = np.abs(expected) >= (
        POLICY.absolute_tolerance / POLICY.relative_tolerance
    )
    max_relative_error = (
        float(np.max(difference[relative_region] / np.abs(expected[relative_region])))
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
        precision=DESCRIPTOR.precision,
        policy=POLICY,
        status="matched" if np.all(difference <= threshold) else "mismatched",
        compared_values=int(difference.size),
        max_absolute_error=float(np.max(difference)),
        max_relative_error=max_relative_error,
        provenance=ExecutionProvenance.current(gpu),
    )


def _candidate_output(
    inputs: PropagationInput, implementation_id: str
) -> tuple[StateBatch, GPUProvenance | None]:
    if implementation_id == NUMPY.id:
        return accelerated(inputs), None
    if implementation_id == CUPY.id:
        cupy = cupy_backend.load()
        return cupy_backend.accelerated(inputs, cupy), cupy_backend.provenance(cupy)
    raise KeyError(implementation_id)


def availability(implementation_id: str) -> tuple[bool, str]:
    if implementation_id in (DESCRIPTOR.reference.id, NUMPY.id):
        return True, "available in the base package"
    if implementation_id == CUPY.id:
        return cupy_backend.availability()
    raise KeyError(implementation_id)


def verify(case_id: str, implementation_id: str = NUMPY.id) -> ValidationReceipt:
    inputs = case(case_id)
    actual, gpu = _candidate_output(inputs, implementation_id)
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
    if type(repeat) is not int or repeat <= 0:
        raise ValueError("repeat must be a positive integer")
    if type(warmup) is not int or warmup < 0:
        raise ValueError("warmup must be a nonnegative integer")
    if baseline_id not in (DESCRIPTOR.reference.id, NUMPY.id):
        raise KeyError(baseline_id)
    inputs = case(case_id)
    actual, gpu = _candidate_output(inputs, implementation_id)
    candidate = next(
        item for item in DESCRIPTOR.candidates if item.id == implementation_id
    )
    validation = validate(case_id, reference(inputs), actual, candidate, gpu)
    if validation.status != "matched":
        raise ValueError("benchmark validation failed")
    baseline_action: Callable[[], object] = partial(
        reference if baseline_id == DESCRIPTOR.reference.id else accelerated, inputs
    )
    baseline = DESCRIPTOR.reference if baseline_id == DESCRIPTOR.reference.id else NUMPY
    candidate_action: Callable[[], object]
    synchronize: Callable[[], None]
    if implementation_id == CUPY.id:
        cupy = cupy_backend.load()
        candidate_action, synchronize = cupy_backend.prepare_benchmark(
            inputs, timing_scope, cupy
        )
        transfers = (
            TransferInclusion.INCLUDED
            if timing_scope == TimingScope.END_TO_END
            else TransferInclusion.EXCLUDED
        )
        candidate_synchronization = Synchronization.CUDA_STREAM
    else:
        candidate_action = partial(accelerated, inputs)
        synchronize = _no_sync
        transfers = TransferInclusion.NOT_APPLICABLE
        candidate_synchronization = Synchronization.SYNCHRONOUS
    for _ in range(warmup):
        baseline_action()
        result = candidate_action()
        synchronize()
        del result
    baseline_times: list[int] = []
    candidate_times: list[int] = []
    for _ in range(repeat):
        baseline_times.append(_timed(baseline_action, _no_sync))
        candidate_times.append(_timed(candidate_action, synchronize))
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
        baseline_times_ns=tuple(baseline_times),
        candidate_times_ns=tuple(candidate_times),
        median_baseline_ns=median_baseline,
        median_candidate_ns=median_candidate,
        speedup=median_baseline / median_candidate,
        provenance=ExecutionProvenance.current(gpu),
    )
