"""Check committed benchmark receipts before they become claims."""

import hashlib
import json
import math
import statistics
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, cast

from raddle.contracts import (
    BenchmarkReceipt,
    ExecutionProvenance,
    GPUProvenance,
    ImplementationIdentity,
    ValidationPolicy,
    ValidationReceipt,
    _json,
)
from raddle.registry import get_accelerator


@dataclass(frozen=True)
class BenchmarkClaim:
    accelerator_id: str
    case_id: str
    workload: dict[str, object]
    baseline: ImplementationIdentity
    candidate: ImplementationIdentity
    speedup: float
    timing_scope: str
    validation_status: str
    gpu_model: str | None
    raddle_version: str
    receipt_path: str


def _keys(data: Any, expected: set[str]) -> None:
    if not isinstance(data, dict) or set(data) != expected:
        raise ValueError("unexpected receipt fields")


def _fields(model: type[Any]) -> set[str]:
    return {field.name for field in fields(model)}


def _provenance(data: Any) -> None:
    _keys(data, _fields(ExecutionProvenance))
    if data["gpu"] is not None:
        _keys(data["gpu"], _fields(GPUProvenance))
        if not isinstance(data["gpu"]["model"], str) or not data["gpu"]["model"]:
            raise ValueError("GPU model is required")
    for name in (
        "python_version",
        "raddle_version",
        "numpy_version",
        "operating_system",
        "architecture",
        "processor",
    ):
        if not isinstance(data[name], str) or not data[name]:
            raise ValueError(f"invalid provenance {name}")
    if data["logical_cpu_count"] is not None and (
        type(data["logical_cpu_count"]) is not int or data["logical_cpu_count"] <= 0
    ):
        raise ValueError("invalid CPU count")


def check_receipt(data: Any) -> dict[str, Any]:
    """Reject malformed evidence; the digest detects casual edits, not forgery."""
    _keys(data, _fields(BenchmarkReceipt) | {"content_sha256"})
    digest = data.pop("content_sha256")
    try:
        if (
            not isinstance(digest, str)
            or hashlib.sha256(_json(data).encode()).hexdigest() != digest
        ):
            raise ValueError("receipt digest mismatch")
        if (
            data["schema_version"] != 3
            or data["clock"] != "perf_counter_ns"
            or data["setup_included"] is not False
        ):
            raise ValueError("unsupported benchmark schema or timing")
        registered = get_accelerator(data["accelerator_id"])
        descriptor = registered.descriptor
        if data["accelerator_version"] != descriptor.version:
            raise ValueError("accelerator version mismatch")
        case = next(item for item in descriptor.cases if item.id == data["case_id"])
        if data["workload"] != asdict(case):
            raise ValueError("workload differs from canonical case")
        identities = (descriptor.reference, *descriptor.candidates)
        _keys(data["baseline"], _fields(ImplementationIdentity))
        if data["baseline"] not in [asdict(item) for item in identities]:
            raise ValueError("unknown baseline identity")
        validation = data["validation"]
        _keys(validation, _fields(ValidationReceipt))
        for key in ("reference", "candidate"):
            _keys(validation[key], _fields(ImplementationIdentity))
        _keys(validation["policy"], _fields(ValidationPolicy))
        _provenance(validation["provenance"])
        _provenance(data["provenance"])
        if validation["schema_version"] != 2 or validation["status"] != "matched":
            raise ValueError("validation must match")
        if (
            validation["accelerator_id"],
            validation["accelerator_version"],
            validation["case_id"],
        ) != (descriptor.id, descriptor.version, case.id):
            raise ValueError("validation identity mismatch")
        if validation["reference"] != asdict(descriptor.reference) or validation[
            "candidate"
        ] not in [asdict(item) for item in descriptor.candidates]:
            raise ValueError("validation implementation mismatch")
        if (
            validation["policy"] != asdict(descriptor.validation_policy)
            or validation["precision"] != descriptor.precision
        ):
            raise ValueError("validation policy mismatch")
        if data["provenance"] != validation["provenance"]:
            raise ValueError("execution provenance mismatch")
        if data["timing_scope"] not in ("end_to_end", "compute_only") or data[
            "host_device_transfers"
        ] not in ("included", "excluded", "not_applicable"):
            raise ValueError("invalid timing scope or transfer policy")
        if data["baseline_synchronization"] != "synchronous_call":
            raise ValueError("invalid baseline synchronization")
        gpu = validation["candidate"]["id"] == "cupy.vectorized"
        if data["candidate_synchronization"] != (
            "cuda_current_stream_pre_post" if gpu else "synchronous_call"
        ):
            raise ValueError("invalid candidate synchronization")
        if data["host_device_transfers"] != (
            ("included" if data["timing_scope"] == "end_to_end" else "excluded")
            if gpu
            else "not_applicable"
        ):
            raise ValueError("transfer policy mismatch")
        if gpu != (data["provenance"]["gpu"] is not None):
            raise ValueError("GPU provenance mismatch")
        if (
            type(data["warmup"]) is not int
            or data["warmup"] < 0
            or type(data["repeat"]) is not int
            or data["repeat"] <= 0
        ):
            raise ValueError("invalid repetition counts")
        for path, median_key in (
            ("baseline_times_ns", "median_baseline_ns"),
            ("candidate_times_ns", "median_candidate_ns"),
        ):
            values = data[path]
            if (
                not isinstance(values, list)
                or len(values) != data["repeat"]
                or any(type(value) is not int or value <= 0 for value in values)
            ):
                raise ValueError(f"invalid {path}")
            if data[median_key] != statistics.median(values):
                raise ValueError(f"invalid {median_key}")
        if not math.isclose(
            data["speedup"],
            data["median_baseline_ns"] / data["median_candidate_ns"],
            rel_tol=1e-14,
        ):
            raise ValueError("invalid speedup")
        if (
            validation["compared_values"] <= 0
            or validation["max_absolute_error"] < 0
            or validation["max_relative_error"] < 0
        ):
            raise ValueError("invalid validation diagnostics")
        if not all(
            math.isfinite(value)
            for value in (
                data["speedup"],
                validation["max_absolute_error"],
                validation["max_relative_error"],
            )
        ):
            raise ValueError("nonfinite evidence")
    finally:
        data["content_sha256"] = digest
    return cast(dict[str, Any], data)


def read_receipt(path: Path) -> dict[str, Any]:
    data: Any = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )
    checked = check_receipt(data)
    if path.read_text(encoding="utf-8") != _json(checked) + "\n":
        raise ValueError("receipt is not canonical JSON")
    return checked


def published_claims() -> tuple[BenchmarkClaim, ...]:
    root = Path(__file__).parent / "receipts"
    claims = []
    for path in sorted(root.rglob("*.json")):
        data = read_receipt(path)
        claims.append(
            BenchmarkClaim(
                accelerator_id=data["accelerator_id"],
                case_id=data["case_id"],
                workload=data["workload"],
                baseline=ImplementationIdentity(**data["baseline"]),
                candidate=ImplementationIdentity(**data["validation"]["candidate"]),
                speedup=data["speedup"],
                timing_scope=data["timing_scope"],
                validation_status=data["validation"]["status"],
                gpu_model=(data["provenance"]["gpu"] or {}).get("model"),
                raddle_version=data["provenance"]["raddle_version"],
                receipt_path=f"src/raddle/receipts/{path.parent.name}/{path.name}",
            )
        )
    return tuple(claims)


def main() -> int:
    root = (
        Path(sys.argv[1]) if len(sys.argv) == 2 else Path(__file__).parent / "receipts"
    )
    paths = sorted(root.rglob("*.json"))
    if not paths:
        raise ValueError("no benchmark receipts found")
    for path in paths:
        receipt = read_receipt(path)
        if path.parent.name != receipt["accelerator_id"]:
            raise ValueError(f"receipt is in the wrong accelerator directory: {path}")
        print(f"valid {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
