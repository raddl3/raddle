"""Versioned public metadata and evidence for Raddle accelerators."""

import json
import os
import platform
from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np

from raddle import __version__


def _json(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class ImplementationIdentity:
    id: str
    version: str


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
class AcceleratorDescriptor:
    id: str
    version: str
    name: str
    reference: ImplementationIdentity
    candidate: ImplementationIdentity
    input_contract: str
    output_contract: str
    precision: Literal["float64"]
    supported_environment: str
    validation_policy: ValidationPolicy
    cases: tuple[CaseDescriptor, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return _json(self.to_dict())


@dataclass(frozen=True)
class ExecutionProvenance:
    python_version: str
    raddle_version: str
    numpy_version: str
    operating_system: str
    architecture: str
    processor: str
    logical_cpu_count: int | None

    @classmethod
    def current(cls) -> "ExecutionProvenance":
        # Explicit fields prevent hostname, username, paths, and env leakage.
        return cls(
            python_version=platform.python_version(),
            raddle_version=__version__,
            numpy_version=np.__version__,
            operating_system=platform.system(),
            architecture=platform.machine(),
            processor=platform.processor() or platform.machine(),
            logical_cpu_count=os.cpu_count(),
        )


@dataclass(frozen=True)
class ValidationReceipt:
    schema_version: Literal[1]
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
    schema_version: Literal[1]
    accelerator_id: str
    accelerator_version: str
    case_id: str
    validation: ValidationReceipt
    clock: Literal["perf_counter_ns"]
    warmup: int
    repeat: int
    reference_times_ns: tuple[int, ...]
    candidate_times_ns: tuple[int, ...]
    median_reference_ns: float
    median_candidate_ns: float
    speedup: float
    provenance: ExecutionProvenance

    def __post_init__(self) -> None:
        if self.validation.status != "matched":
            raise ValueError("benchmark evidence requires matched validation")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return _json(self.to_dict())
