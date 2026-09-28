"""Versioned public metadata and evidence for Raddle accelerators."""

import hashlib
import json
import os
import platform
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Literal

import numpy as np

from raddle import __version__


def _json(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class ImplementationIdentity:
    id: str
    version: str
    optional_extra: str | None = None


@dataclass(frozen=True)
class ValidationPolicy:
    id: str
    absolute_tolerance: float
    relative_tolerance: float


@dataclass(frozen=True)
class CaseDescriptor:
    id: str
    trajectories: int
    mu: float
    dt: float
    steps: int


@dataclass(frozen=True)
class BootstrapCaseDescriptor:
    id: str
    sample_size: int
    resamples: int
    seed: int
    confidence_level: float
    sample_rule: Literal["linear_0_1_v1"] = "linear_0_1_v1"


@dataclass(frozen=True)
class AcceleratorDescriptor:
    id: str
    version: str
    name: str
    reference: ImplementationIdentity
    candidates: tuple[ImplementationIdentity, ...]
    input_contract: str
    output_contract: str
    precision: Literal["float64"]
    supported_environment: str
    validation_policy: ValidationPolicy
    cases: tuple[CaseDescriptor | BootstrapCaseDescriptor, ...]
    algorithm: str | None = None

    @property
    def candidate(self) -> ImplementationIdentity:
        """The default CPU candidate retained for v0.1 callers."""
        return self.candidates[0]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["candidate"] = asdict(self.candidate)
        return data

    def to_json(self) -> str:
        return _json(self.to_dict())


@dataclass(frozen=True)
class GPUProvenance:
    model: str
    gpu_count_used: int
    cuda_runtime_version: int
    cuda_driver_version: int
    cupy_version: str


@dataclass(frozen=True)
class ExecutionProvenance:
    python_version: str
    raddle_version: str
    numpy_version: str
    operating_system: str
    architecture: str
    processor: str
    logical_cpu_count: int | None
    gpu: GPUProvenance | None = None

    @classmethod
    def current(cls, gpu: GPUProvenance | None = None) -> "ExecutionProvenance":
        # Explicit fields prevent hostname, username, paths, and env leakage.
        return cls(
            python_version=platform.python_version(),
            raddle_version=__version__,
            numpy_version=np.__version__,
            operating_system=platform.system(),
            architecture=platform.machine(),
            processor=platform.processor() or platform.machine(),
            logical_cpu_count=os.cpu_count(),
            gpu=gpu,
        )


class TimingScope(StrEnum):
    END_TO_END = "end_to_end"
    COMPUTE_ONLY = "compute_only"


class TransferInclusion(StrEnum):
    INCLUDED = "included"
    EXCLUDED = "excluded"
    NOT_APPLICABLE = "not_applicable"


class Synchronization(StrEnum):
    SYNCHRONOUS = "synchronous_call"
    CUDA_STREAM = "cuda_current_stream_pre_post"


@dataclass(frozen=True)
class ValidationReceipt:
    schema_version: Literal[2]
    accelerator_id: str
    accelerator_version: str
    case_id: str
    reference: ImplementationIdentity
    candidate: ImplementationIdentity
    precision: Literal["float64"]
    policy: ValidationPolicy
    status: Literal["matched", "mismatched"]
    compared_values: int
    max_absolute_error: float
    max_relative_error: float
    provenance: ExecutionProvenance

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return _json(self.to_dict())


@dataclass(frozen=True)
class BenchmarkReceipt:
    schema_version: Literal[3]
    accelerator_id: str
    accelerator_version: str
    case_id: str
    workload: dict[str, object]
    validation: ValidationReceipt
    clock: Literal["perf_counter_ns"]
    timing_scope: TimingScope
    setup_included: bool
    host_device_transfers: TransferInclusion
    baseline: ImplementationIdentity
    baseline_synchronization: Synchronization
    candidate_synchronization: Synchronization
    warmup: int
    repeat: int
    baseline_times_ns: tuple[int, ...]
    candidate_times_ns: tuple[int, ...]
    median_baseline_ns: float
    median_candidate_ns: float
    speedup: float
    provenance: ExecutionProvenance

    def __post_init__(self) -> None:
        if self.validation.status != "matched":
            raise ValueError("benchmark evidence requires matched validation")
        if self.case_id != self.validation.case_id:
            raise ValueError("benchmark and validation case must match")
        if self.accelerator_id != self.validation.accelerator_id:
            raise ValueError("benchmark and validation accelerator must match")

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["content_sha256"] = hashlib.sha256(_json(data).encode()).hexdigest()
        return data

    def to_json(self) -> str:
        return _json(self.to_dict())
