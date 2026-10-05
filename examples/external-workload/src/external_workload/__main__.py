"""Complete public Forge integration; see the example README for invocation."""

import cProfile
import hashlib
import importlib.util
import json
import shutil
import statistics
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from time import perf_counter_ns
from typing import cast
from zipfile import ZipFile

import numpy as np
from numpy.typing import NDArray

from external_workload import reference
from raddle import __version__
from raddle.artifact import create_external_artifact, read_artifact
from raddle.contracts import (
    AcceleratorDescriptor,
    ExecutionProvenance,
    ExternalCaseDescriptor,
    ImplementationIdentity,
    ValidationPolicy,
    ValidationReceipt,
)
from raddle.forge import (
    AccelerationTarget,
    BenchmarkResult,
    ForgeCampaign,
    ForgeContract,
)

SIZE = 100_000
CASE = ExternalCaseDescriptor("integration.square", {"size": SIZE, "rule": "arange"})
POLICY = ValidationPolicy("square.exact.v1", 0.0, 0.0)
REFERENCE = ImplementationIdentity("numpy.square.scalar", np.__version__)
CANDIDATE = ImplementationIdentity("external_workload.square.batch", "0.1.0")
DESCRIPTOR = AcceleratorDescriptor(
    "example.square",
    "0.1.0",
    "External integration example",
    REFERENCE,
    (CANDIDATE,),
    "float64 arange(size); size=100000",
    "float64 squared values",
    "float64",
    "CPU with NumPy",
    POLICY,
    (CASE,),
)
Runner = Callable[[int], NDArray[np.float64]]


def measure(call: Callable[[], object]) -> dict[str, object]:
    call()  # warm-up is outside the measured boundary
    samples = []
    for _ in range(3):
        start = perf_counter_ns()
        call()
        samples.append(perf_counter_ns() - start)
    return {
        "clock": "perf_counter_ns",
        "warmup": 1,
        "repeat": 3,
        "provenance": asdict(ExecutionProvenance.current()),
        "times_ns": samples,
        "median_ns": statistics.median(samples),
        "scope": "end_to_end",
    }


def validate(expected: object, actual: object) -> ValidationReceipt:
    a, b = np.asarray(expected), np.asarray(actual)
    if a.shape != b.shape or a.dtype != b.dtype:
        raise ValueError("candidate shape or dtype mismatch")
    matched = np.array_equal(a, b)
    error = float(np.max(np.abs(a - b)))
    relative = float(np.max(np.abs(a - b) / np.maximum(np.abs(a), 1.0)))
    return ValidationReceipt(
        2,
        DESCRIPTOR.id,
        DESCRIPTOR.version,
        CASE.id,
        REFERENCE,
        CANDIDATE,
        "float64",
        POLICY,
        "matched" if matched else "mismatched",
        SIZE,
        error,
        relative,
        ExecutionProvenance.current(),
    )


def build(snapshot: Path) -> tuple[object, object]:
    # Load the immutable snapshot, never the mutable producer's working file.
    spec = importlib.util.spec_from_file_location("evaluated_candidate", snapshot)
    if spec is None or spec.loader is None:
        raise ValueError("candidate cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # trusted workload code only
    return cast(Runner, module.run), {"status": "built", "loader": "importlib"}


def run(
    output: Path, raddle_wheel: Path, *, approve_target: bool = False
) -> ForgeCampaign:
    if output.exists():
        raise ValueError("use a new output directory for this demonstration")
    root = Path(__file__).resolve().parents[2]
    # NumPy publishes the full Git identity of the installed reference implementation.
    revision = "git:" + np.version.git_revision
    reference_identity = {
        "implementation": asdict(REFERENCE),
        "revision": revision,
        "adapter_sha256": hashlib.sha256(
            (root / "src/external_workload/__init__.py").read_bytes()
        ).hexdigest(),
    }
    target = AccelerationTarget(
        target_id="external-square.v1",
        invocation="external_workload.reference(100000)",
        representative_case=json.dumps(asdict(CASE), sort_keys=True),
        objective="warm latency",
        timing_boundary=(
            "reference(size), input allocation through output; warm-up excluded"
        ),
        trusted_reference=json.dumps(reference_identity, sort_keys=True),
        included_paths=("src/external_workload/__init__.py:reference",),
        excluded_paths=("process initialization", "wheel build", "artifact packaging"),
        approval="User approved the fixed demonstration target via approve_target=True",
        compute_constraints=("local CPU with pinned NumPy",),
    )
    if not approve_target:
        proposal = asdict(target)
        proposal["approval"] = "pending"
        print(json.dumps(proposal, indent=2, sort_keys=True))
        print("Is this the workload you want accelerated?")
        raise ValueError("target approval required; rerun with --approve-target")
    contract = ForgeContract(
        "external-square",
        reference_identity,
        asdict(CASE),
        asdict(POLICY),
        1,
        target=target,
    )
    baseline = measure(lambda: reference(SIZE))
    profiler = cProfile.Profile()
    profiler.runcall(reference, SIZE)
    entries = sorted(
        profiler.getstats(), key=lambda entry: entry.totaltime, reverse=True
    )
    profile: dict[str, object] = {
        "profiler": "cProfile",
        "boundary": "reference(size), allocation included",
        "top": [
            {
                "function": entry.code
                if isinstance(entry.code, str)
                else entry.code.co_name,
                "calls": entry.callcount,
                "cumulative_seconds": entry.totaltime,
            }
            for entry in entries[:5]
        ],
    }
    campaign = ForgeCampaign(
        output / "forge.jsonl",
        contract,
        baseline_id="reference",
        baseline_score=float(cast(float, baseline["median_ns"])),
        baseline_evidence=baseline,
        profile_evidence=profile,
    )
    expected = reference(SIZE)

    def check(candidate: object) -> dict[str, object]:
        return validate(expected, cast(Runner, candidate)(SIZE)).to_dict()

    def benchmark(candidate: object) -> BenchmarkResult:
        evidence = measure(lambda: cast(Runner, candidate)(SIZE))
        return BenchmarkResult(evidence, float(cast(float, evidence["median_ns"])))

    evaluation = campaign.evaluate(
        candidate_source=root / "src/external_workload/candidate.py",
        source_store=output / "candidates",
        experiment_id="batch-square",
        parent_experiment="reference",
        metadata={"purpose": "integration example"},
        build=build,
        validate=check,
        benchmark=benchmark,
    )
    if not evaluation.record["accepted"]:
        raise RuntimeError("no accepted incumbent; inspect ledger, do not package")
    snapshot = campaign.incumbent_source()  # verifies winner bytes against the ledger
    candidate, _ = build(snapshot)
    # Build a workload wheel containing those exact accepted bytes.
    packaged = output / "package"
    shutil.copytree(root / "src", packaged / "src")
    shutil.copyfile(root / "pyproject.toml", packaged / "pyproject.toml")
    shutil.copyfile(snapshot, packaged / "src/external_workload/candidate.py")
    subprocess.run(
        [
            "uv",
            "build",
            "--wheel",
            "--out-dir",
            str((output / "wheels").resolve()),
            str(packaged.resolve()),
        ],
        check=True,
    )
    workload_wheel = next((output / "wheels").glob("external_workload-*.whl"))
    with ZipFile(workload_wheel) as wheel:
        if wheel.read("external_workload/candidate.py") != snapshot.read_bytes():
            raise ValueError("packaged candidate differs from incumbent")
    manifest = create_external_artifact(
        descriptor=DESCRIPTOR,
        case=CASE,
        reference=lambda: reference(SIZE),
        candidate=lambda: cast(Runner, candidate)(SIZE),
        validate=validate,
        inputs_json=json.dumps({"case": asdict(CASE)}),
        reference_source_url="https://github.com/numpy/numpy",
        reference_source_revision=revision,
        reference_invocation="external_workload.reference(100000): scalar numpy.square",
        candidate_invocation="external_workload.candidate.run(100000)",
        validation_method="exact shape, dtype and every value",
        profile=profile,
        dependencies={
            "numpy": np.__version__,
            "raddle": __version__,
            "external-workload": "0.1.0",
        },
        raddle_wheel=raddle_wheel,
        workload_wheel=workload_wheel,
        candidate_package="external-workload",
        candidate_package_version="0.1.0",
        candidate_source_member="external_workload/candidate.py",
        workload_package="external-workload",
        workload_package_version="0.1.0",
        lock_file=root / "uv.lock",
        output=output / "artifacts",
        repeat=3,
        warmup=1,
        reproduce=(
            "uv run --no-project --python 3.12 --with ./"
            + raddle_wheel.name
            + " --with numpy=="
            + np.__version__
            + " --with ./"
            + workload_wheel.name
            + " python -c 'from external_workload import reference; "
            "from external_workload.candidate import run; "
            "from external_workload.__main__ import measure, validate; "
            "print(validate(reference(100000), run(100000)).to_json()); "
            "print(measure(lambda: reference(100000))); "
            "print(measure(lambda: run(100000)))'",
        ),
    )
    checked = read_artifact(output / "artifacts")
    if checked != manifest:
        raise ValueError("artifact readback differs from created manifest")
    if manifest.candidate_source_revision != (
        "sha256:" + campaign.status()["incumbent"]["candidate_source_hash"]
    ):
        raise ValueError("artifact readback disagrees with Forge incumbent")
    return campaign


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4) or (
        len(sys.argv) == 4 and sys.argv[3] != "--approve-target"
    ):
        raise SystemExit(
            "usage: python -m external_workload OUTPUT RADDLE_WHEEL [--approve-target]"
        )
    try:
        result = run(
            Path(sys.argv[1]).resolve(),
            Path(sys.argv[2]).resolve(),
            approve_target=len(sys.argv) == 4,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print("Accepted incumbent:", result.status()["incumbent"]["experiment_id"])
    print("Artifact readback passed. Local timings are integration evidence only.")
