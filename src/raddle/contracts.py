"""Small, stable public accelerator and validation contracts."""

from dataclasses import asdict, dataclass
from typing import Literal


@dataclass(frozen=True)
class AcceleratorDescriptor:
    id: str
    version: str
    reference: str
    accelerated: str
    input_contract: str
    output_contract: str
    validation: str
    benchmark_case: str
    supported_environment: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ValidationReceipt:
    schema_version: Literal[1]
    accelerator_id: str
    accelerator_version: str
    case_id: str
    reference: str
    accelerated: str
    runtime: str
    runtime_version: str
    reference_result: int
    accelerated_result: int
    validation: Literal["matched", "mismatched"]

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)
