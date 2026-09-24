"""Exercise the optional boundary on CPU; real CUDA tests live in test_gpu.py."""

import importlib
import importlib.util

import numpy as np
from pytest import MonkeyPatch

from raddle import cupy_backend
from raddle.contracts import TimingScope, TransferInclusion
from raddle.orbit import CUPY, benchmark, verify


class FakeStream:
    def __init__(self) -> None:
        self.synchronizations = 0

    def synchronize(self) -> None:
        self.synchronizations += 1


class FakeRuntime:
    CUDARuntimeError = RuntimeError

    def getDeviceCount(self) -> int:
        return 1

    def getDevice(self) -> int:
        return 0

    def getDeviceProperties(self, device: int) -> dict[str, bytes]:
        assert device == 0
        return {"name": b"Synthetic CUDA device"}

    def runtimeGetVersion(self) -> int:
        return 12090

    def driverGetVersion(self) -> int:
        return 12090


class FakeCuda:
    def __init__(self) -> None:
        self.runtime = FakeRuntime()
        self.stream = FakeStream()

    def get_current_stream(self) -> FakeStream:
        return self.stream


class FakeCupy:
    __version__ = "test-only"
    float64 = np.float64
    asarray = staticmethod(np.asarray)
    array = staticmethod(np.array)
    sum = staticmethod(np.sum)
    sqrt = staticmethod(np.sqrt)
    concatenate = staticmethod(np.concatenate)
    isfinite = staticmethod(np.isfinite)
    asnumpy = staticmethod(np.asarray)

    def __init__(self) -> None:
        self.cuda = FakeCuda()


def test_optional_boundary_and_scopes(monkeypatch: MonkeyPatch) -> None:
    fake = FakeCupy()
    monkeypatch.setattr(importlib.util, "find_spec", lambda _: object())
    monkeypatch.setattr(importlib, "import_module", lambda _: fake)
    assert cupy_backend.load() is fake
    assert cupy_backend.availability() == (True, "available on this host")
    validation = verify("circular.small", CUPY.id)
    assert validation.status == "matched"
    assert validation.provenance.gpu is not None
    assert validation.provenance.gpu.model == "Synthetic CUDA device"
    for scope, transfers in (
        (TimingScope.COMPUTE_ONLY, TransferInclusion.EXCLUDED),
        (TimingScope.END_TO_END, TransferInclusion.INCLUDED),
    ):
        receipt = benchmark(
            "circular.small",
            repeat=1,
            warmup=1,
            implementation_id=CUPY.id,
            timing_scope=scope,
            baseline_id="numpy.vectorized",
        )
        assert receipt.validation.status == "matched"
        assert receipt.host_device_transfers == transfers
        assert receipt.provenance.gpu is not None
    assert fake.cuda.stream.synchronizations >= 6
