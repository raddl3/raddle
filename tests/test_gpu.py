"""Run only when the optional CuPy backend and a CUDA device are available."""

import numpy as np
import pytest
from pytest import MonkeyPatch

from raddle import bootstrap
from raddle.bootstrap import CUPY as BOOTSTRAP_CUPY
from raddle.bootstrap import benchmark as bootstrap_benchmark
from raddle.bootstrap import verify as bootstrap_verify
from raddle.contracts import Synchronization, TimingScope, TransferInclusion
from raddle.cupy_backend import load
from raddle.orbit import CUPY, availability, benchmark, verify


@pytest.fixture
def cuda_ready() -> None:
    available, reason = availability(CUPY.id)
    if not available:
        pytest.skip(reason)


def test_gpu_validation(cuda_ready: None) -> None:
    receipt = verify("circular.small", CUPY.id)
    assert receipt.status == "matched"
    assert receipt.candidate == CUPY
    assert receipt.provenance.gpu is not None
    assert receipt.provenance.gpu.gpu_count_used == 1


@pytest.mark.parametrize("scope", [TimingScope.COMPUTE_ONLY, TimingScope.END_TO_END])
def test_gpu_benchmark_scopes(cuda_ready: None, scope: TimingScope) -> None:
    receipt = benchmark(
        "circular.small",
        repeat=1,
        warmup=1,
        implementation_id=CUPY.id,
        timing_scope=scope,
        baseline_id="numpy.vectorized",
    )
    assert receipt.validation.status == "matched"
    assert receipt.candidate_synchronization == Synchronization.CUDA_STREAM
    assert receipt.host_device_transfers == (
        TransferInclusion.INCLUDED
        if scope == TimingScope.END_TO_END
        else TransferInclusion.EXCLUDED
    )
    assert receipt.median_candidate_ns > 0


def test_bootstrap_gpu(cuda_ready: None) -> None:
    assert bootstrap_verify("bootstrap.small", BOOTSTRAP_CUPY.id).status == "matched"
    for scope in (TimingScope.END_TO_END, TimingScope.COMPUTE_ONLY):
        receipt = bootstrap_benchmark(
            "bootstrap.small", 1, 0, BOOTSTRAP_CUPY.id, scope, "numpy.vectorized"
        )
        assert receipt.validation.status == "matched"


def test_bootstrap_device_plan_and_fused_semantics(
    cuda_ready: None, monkeypatch: MonkeyPatch
) -> None:
    cp = load()
    monkeypatch.setattr(bootstrap, "CHUNK_INDICES", 257)
    for size in (1, 2, 3, 7, 32, 256, 257):
        for seed in (0, 11, (1 << 64) - 1, (-0x9E3779B97F4A7C15) % (1 << 64)):
            inputs = bootstrap.BootstrapInput(np.linspace(0, 1, size), 11, seed, 0.95)
            expected = np.concatenate(list(bootstrap.plans(inputs)))
            actual = cp.asnumpy(
                cp.concatenate(list(bootstrap.device_plans_for(inputs, cp)))
            )
            np.testing.assert_array_equal(actual, expected)
            np.testing.assert_allclose(
                bootstrap.gpu_accelerated(inputs, cp).distribution,
                bootstrap.reference(inputs).distribution,
                atol=1e-12,
                rtol=1e-12,
            )
    # This seed produces a zero initial draw at logical position zero.
    zero_seed = (-0x9E3779B97F4A7C15) % (1 << 64)
    inputs = bootstrap.BootstrapInput([1.0, 2.0, 3.0], 2, zero_seed, 0.95)
    np.testing.assert_array_equal(
        cp.asnumpy(next(bootstrap.device_plans_for(inputs, cp))),
        next(bootstrap.plans(inputs)),
    )
    assert next(bootstrap.plans(inputs))[0, 0] == 1
    rejected = bootstrap.BootstrapInput(np.arange(10), 2, 0xF8364607E9C949BD, 0.95)
    device = cp.asnumpy(next(bootstrap.device_plans_for(rejected, cp)))
    assert device[0, 0] == 9
    np.testing.assert_array_equal(device, next(bootstrap.plans(rejected)))
