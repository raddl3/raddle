import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest
from pytest import MonkeyPatch

from raddle import orbit
from raddle.artifact import (
    _check_candidate_wheel,
    _external_candidate_wheel,
    _wheel_source,
    create_artifact,
    create_external_artifact,
    read_artifact,
)
from raddle.contracts import (
    AcceleratorDescriptor,
    BenchmarkReceipt,
    ExecutionProvenance,
    ExternalAcceleratorArtifact,
    ExternalCaseDescriptor,
    GPUProvenance,
    ImplementationIdentity,
    Synchronization,
    TimingScope,
    TransferInclusion,
    ValidationPolicy,
    ValidationReceipt,
)
from raddle.evidence import check_receipt, read_receipt


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("wheel")
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(output)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return next(output.glob("raddle-*.whl"))


def test_orbit_fixture_artifact_round_trip(tmp_path: Path, wheel: Path) -> None:
    inputs = orbit.case("circular.small")
    assert np.isfinite(orbit.reference(inputs)).all()
    output = tmp_path / "accelerator"
    manifest = create_artifact("circular.small", wheel, output, repeat=2, warmup=0)
    receipt = read_receipt(output / "benchmark.json")
    assert manifest == read_artifact(output)
    assert manifest.schema_version == 1 and manifest.fixture is True
    assert manifest.reference == orbit.DESCRIPTOR.reference
    assert manifest.candidate == orbit.NUMPY
    assert manifest.baseline.repeat == 2
    assert len(manifest.baseline.times_ns) == 2
    assert manifest.baseline.median_ns > 0
    assert receipt["validation"]["status"] == "matched"
    assert receipt["validation"]["policy"]["absolute_tolerance"] == 1e-11
    assert len(receipt["baseline_times_ns"]) == len(receipt["candidate_times_ns"]) == 2
    assert receipt["median_candidate_ns"] > 0
    assert manifest.baseline.provenance.python_version
    assert manifest.baseline.provenance.operating_system
    assert receipt["provenance"]["numpy_version"]
    assert receipt["provenance"]["logical_cpu_count"]
    assert "--from" in manifest.reproduce[0]
    with ZipFile(output / manifest.wheel_file) as package:
        assert "raddle/orbit.py" in package.namelist()
    reproduced = output / "reproduced"
    create_artifact("circular.small", output / manifest.wheel_file, reproduced, 2, 0)
    assert read_artifact(reproduced).reference == manifest.reference
    assert read_artifact(reproduced).candidate == manifest.candidate
    manifest_path = output / "manifest.json"
    original_manifest = manifest_path.read_text()
    changed_manifest = json.loads(original_manifest)
    changed_manifest["baseline"]["median_ns"] = 1
    manifest_path.write_text(json.dumps(changed_manifest))
    with pytest.raises(ValueError, match="manifest digest"):
        read_artifact(output)
    manifest_path.write_text(original_manifest)
    changed = json.loads((output / "benchmark.json").read_text())
    changed["median_candidate_ns"] = 1
    (output / "benchmark.json").write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="digest"):
        read_artifact(output)


def test_mismatched_candidate_cannot_create_artifact(
    tmp_path: Path, wheel: Path, monkeypatch: MonkeyPatch
) -> None:
    def wrong(inputs: orbit.PropagationInput) -> orbit.StateBatch:
        return np.zeros(np.asarray(inputs.initial_states).shape, dtype=np.float64)

    def forbidden_benchmark(*args: object, **kwargs: object) -> None:
        pytest.fail("candidate timing must not run after failed validation")

    monkeypatch.setattr(orbit, "accelerated", wrong)
    monkeypatch.setattr(orbit, "benchmark", forbidden_benchmark)
    output = tmp_path / "rejected"
    with pytest.raises(ValueError, match="failed reference validation"):
        create_artifact("circular.small", wheel, output, repeat=1, warmup=0)
    assert not output.exists()


def test_external_candidate_source_can_live_in_workload_wheel(
    tmp_path: Path, wheel: Path
) -> None:
    workload_wheel = tmp_path / "candidate_workload-0.1.0-py3-none-any.whl"
    source = b"def candidate():\n    return 1\n"
    with ZipFile(workload_wheel, "w") as package:
        package.writestr(
            "candidate_workload-0.1.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: candidate-workload\nVersion: 0.1.0\n",
        )
        package.writestr("candidate_workload/candidate.py", source)
    selected = _external_candidate_wheel(
        wheel, workload_wheel, "candidate-workload", "candidate-workload"
    )
    _check_candidate_wheel(selected, "candidate-workload", "0.1.0")
    assert _wheel_source(selected, "candidate_workload/candidate.py") == source


def test_external_gpu_receipt_accepts_generic_case_and_float32() -> None:
    reference = ImplementationIdentity("upstream.reference", "abc123")
    candidate = ImplementationIdentity("raddle.reference_control", "0")
    case = ExternalCaseDescriptor("external.smoke", {"shape": [8, 16]})
    policy = ValidationPolicy("upstream.fp32", 1e-4, 1e-4)
    provenance = ExecutionProvenance.current(
        GPUProvenance(
            "NVIDIA A100-SXM4-40GB",
            1,
            12060,
            12040,
            backend="torch",
            backend_version="2.8.0",
        )
    )
    validation = ValidationReceipt(
        schema_version=2,
        accelerator_id="external.example",
        accelerator_version="0.1.0",
        case_id=case.id,
        reference=reference,
        candidate=candidate,
        precision="float32",
        policy=policy,
        status="matched",
        compared_values=128,
        max_absolute_error=0.0,
        max_relative_error=0.0,
        provenance=provenance,
    )
    receipt = json.loads(
        BenchmarkReceipt(
            schema_version=3,
            accelerator_id="external.example",
            accelerator_version="0.1.0",
            case_id=case.id,
            workload=asdict(case),
            validation=validation,
            clock="perf_counter_ns",
            timing_scope=TimingScope.COMPUTE_ONLY,
            setup_included=False,
            host_device_transfers=TransferInclusion.EXCLUDED,
            baseline=reference,
            baseline_synchronization=Synchronization.SYNCHRONOUS,
            candidate_synchronization=Synchronization.CUDA_STREAM,
            warmup=1,
            repeat=1,
            baseline_times_ns=(10,),
            candidate_times_ns=(8,),
            median_baseline_ns=10,
            median_candidate_ns=8,
            speedup=1.25,
            provenance=provenance,
        ).to_json()
    )
    descriptor = AcceleratorDescriptor(
        id="external.example",
        version="0.1.0",
        name="external test",
        reference=reference,
        candidates=(candidate,),
        input_contract="test inputs",
        output_contract="test output",
        precision="float32",
        supported_environment="test",
        validation_policy=policy,
        cases=(case,),
    )
    assert check_receipt(receipt, descriptor)["validation"]["precision"] == "float32"


def test_generic_external_artifact_round_trip_and_legacy_manifest(
    tmp_path: Path, wheel: Path
) -> None:
    upstream_revision = "a" * 40
    case = ExternalCaseDescriptor("external.tiny", {"shape": [2, 2]})
    reference_id = ImplementationIdentity("upstream.numpy", upstream_revision)
    candidate_id = ImplementationIdentity("raddle.reference_control", "0")
    policy = ValidationPolicy("tiny.float64", 1e-4, 1e-4)
    descriptor = AcceleratorDescriptor(
        id="external.tiny",
        version="0.1.0",
        name="tiny external workload",
        reference=reference_id,
        candidates=(candidate_id,),
        input_contract="2x2 float64",
        output_contract="2x2 float64",
        precision="float64",
        supported_environment="test",
        validation_policy=policy,
        cases=(case,),
    )
    values = np.arange(4, dtype=np.float64).reshape(2, 2)

    def matched(expected: object, actual: object) -> ValidationReceipt:
        np.testing.assert_array_equal(expected, actual)
        return ValidationReceipt(
            schema_version=2,
            accelerator_id=descriptor.id,
            accelerator_version=descriptor.version,
            case_id=case.id,
            reference=reference_id,
            candidate=candidate_id,
            precision="float64",
            policy=policy,
            status="matched",
            compared_values=4,
            max_absolute_error=0.0,
            max_relative_error=0.0,
            provenance=ExecutionProvenance.current(),
        )

    workload = tmp_path / "candidate_workload-0.1.0-py3-none-any.whl"
    with ZipFile(workload, "w") as package:
        package.writestr(
            "candidate_workload-0.1.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: candidate-workload\nVersion: 0.1.0\n",
        )
        package.writestr("candidate_workload/candidate.py", b"def run(): return 0\n")
    lock = tmp_path / "uv.lock"
    lock.write_text("version = 1\n", encoding="utf-8")
    output = tmp_path / "artifact"
    create_external_artifact(
        descriptor=descriptor,
        case=case,
        reference=lambda: values,
        candidate=lambda: values.copy(),
        validate=matched,
        inputs_json=json.dumps({"case": asdict(case), "seed": 7}),
        reference_source_url="https://example.org/reference.git",
        reference_source_revision=f"git:{upstream_revision}",
        reference_invocation="upstream NumPy call",
        candidate_invocation="reference control call",
        validation_method="upstream tolerance",
        profile={"profiler": "test", "top": [{"function": "reference"}]},
        dependencies={
            "raddle": "0.3.0",
            "candidate-workload": "0.1.0",
            "upstream": upstream_revision,
        },
        raddle_wheel=wheel,
        workload_wheel=workload,
        candidate_package="candidate-workload",
        candidate_package_version="0.1.0",
        candidate_source_member="candidate_workload/candidate.py",
        workload_package="candidate-workload",
        workload_package_version="0.1.0",
        lock_file=lock,
        output=output,
        repeat=1,
        warmup=0,
        precision="float64",
        reproduce=("raddle-bench reproduce --task external.tiny",),
    )
    artifact = read_artifact(output)
    assert isinstance(artifact, ExternalAcceleratorArtifact)
    assert artifact.case_id == case.id
    assert artifact.precision == "float64"
    assert artifact.workload == asdict(case)
    assert artifact.reproduce == ("raddle-bench reproduce --task external.tiny",)
    manifest_path = output / "manifest.json"
    legacy = json.loads(manifest_path.read_text(encoding="utf-8"))
    legacy.pop("precision")
    payload = {key: value for key, value in legacy.items() if key != "content_sha256"}
    legacy["content_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(legacy, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    legacy_artifact = read_artifact(output)
    assert isinstance(legacy_artifact, ExternalAcceleratorArtifact)
    assert legacy_artifact.precision == "float64"
