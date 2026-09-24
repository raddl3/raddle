"""Run only when the optional CuPy backend and a CUDA device are available."""

import pytest

from raddle.contracts import Synchronization, TimingScope, TransferInclusion
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
