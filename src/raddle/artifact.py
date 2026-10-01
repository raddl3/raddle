"""Build one inspectable Accelerator artifact from the orbit fixture."""

import hashlib
import json
import shlex
import shutil
import statistics
import time
import zipfile
from collections.abc import Callable
from dataclasses import asdict, fields
from email.parser import Parser
from pathlib import Path
from typing import Any, cast

from raddle import __version__, orbit
from raddle.contracts import (
    AcceleratorArtifact,
    AcceleratorDescriptor,
    BenchmarkReceipt,
    CaseDescriptor,
    ExecutionProvenance,
    ExternalAcceleratorArtifact,
    ExternalCaseDescriptor,
    GPUProvenance,
    ImplementationIdentity,
    ReferenceBaseline,
    Synchronization,
    TimingScope,
    TransferInclusion,
    ValidationPolicy,
    ValidationReceipt,
    _json,
)
from raddle.evidence import read_receipt

VALIDATION_METHOD = (
    "elementwise |candidate-reference| <= absolute_tolerance "
    "+ relative_tolerance*|reference|; finite output and matching shape"
)


def _reproduce(
    case_id: str, wheel_name: str, repeat: int, warmup: int
) -> tuple[str, ...]:
    command = f"uvx --from {shlex.quote('./' + wheel_name)} raddle"
    return (
        f"{command} artifact --case {case_id} "
        f"--wheel {shlex.quote('./' + wheel_name)} --output ./reproduced "
        f"--repeat {repeat} --warmup {warmup}",
        f"{command} verify {orbit.DESCRIPTOR.id} --case {case_id} "
        f"--implementation {orbit.NUMPY.id}",
        f"{command} benchmark {orbit.DESCRIPTOR.id} --case {case_id} "
        f"--implementation {orbit.NUMPY.id} --repeat {repeat} --warmup {warmup}",
    )


def _sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _check_wheel(path: Path, version: str) -> None:
    if path.suffix != ".whl":
        raise ValueError("artifact requires a Raddle wheel")
    try:
        with zipfile.ZipFile(path) as wheel:
            metadata = next(
                name
                for name in wheel.namelist()
                if name.endswith(".dist-info/METADATA")
            )
            details = Parser().parsestr(wheel.read(metadata).decode("utf-8"))
    except (
        OSError,
        ValueError,
        KeyError,
        StopIteration,
        UnicodeError,
        zipfile.BadZipFile,
    ) as error:
        raise ValueError("invalid Raddle wheel") from error
    if details.get("Name", "").lower() != "raddle" or details.get("Version") != version:
        raise ValueError("wheel does not match this Raddle version")


def _check_runtime_matches_wheel(path: Path) -> None:
    package_root = Path(__file__).parent
    with zipfile.ZipFile(path) as wheel:
        for source in package_root.rglob("*.py"):
            name = "raddle/" + source.relative_to(package_root).as_posix()
            if name not in wheel.namelist() or wheel.read(name) != source.read_bytes():
                raise ValueError(f"wheel differs from measured Raddle code: {name}")


def create_artifact(
    case_id: str,
    wheel: Path,
    output: Path,
    repeat: int = 3,
    warmup: int = 1,
) -> AcceleratorArtifact:
    """Measure reference first; package only a validated candidate."""
    if output.exists():
        raise ValueError(f"artifact output already exists: {output}")
    if type(repeat) is not int or repeat <= 0 or type(warmup) is not int or warmup < 0:
        raise ValueError("repeat must be positive and warmup nonnegative")
    _check_wheel(wheel, __version__)
    _check_runtime_matches_wheel(wheel)
    inputs = orbit.case(case_id)
    for _ in range(warmup):
        orbit.reference(inputs)
    times = []
    for _ in range(repeat):
        start = time.perf_counter_ns()
        orbit.reference(inputs)
        times.append(time.perf_counter_ns() - start)
    baseline = ReferenceBaseline(
        invocation=f"raddle.orbit.reference(raddle.orbit.case({case_id!r}))",
        clock="perf_counter_ns",
        warmup=warmup,
        repeat=repeat,
        times_ns=tuple(times),
        median_ns=statistics.median(times),
        provenance=ExecutionProvenance.current(),
    )
    validation = orbit.verify(case_id, orbit.NUMPY.id)
    if validation.status != "matched":
        raise ValueError("candidate failed reference validation; no artifact created")
    benchmark = orbit.benchmark(case_id, repeat, warmup, orbit.NUMPY.id)
    candidate = validation.candidate
    wheel_name = wheel.name
    manifest = AcceleratorArtifact(
        schema_version=1,
        fixture=True,
        accelerator_id=orbit.DESCRIPTOR.id,
        accelerator_version=orbit.DESCRIPTOR.version,
        case_id=case_id,
        reference=orbit.DESCRIPTOR.reference,
        candidate=candidate,
        reference_invocation=baseline.invocation,
        candidate_invocation=f"raddle.orbit.accelerated(raddle.orbit.case({case_id!r}))",
        input_domain=orbit.DESCRIPTOR.input_contract,
        validation_method=VALIDATION_METHOD,
        baseline=baseline,
        benchmark_file="benchmark.json",
        benchmark_sha256=hashlib.sha256(
            (benchmark.to_json() + "\n").encode("utf-8")
        ).hexdigest(),
        wheel_file=wheel_name,
        wheel_sha256=_sha256(wheel),
        reproduce=_reproduce(case_id, wheel_name, repeat, warmup),
    )
    output.mkdir(parents=True)
    shutil.copyfile(wheel, output / wheel_name)
    (output / "benchmark.json").write_text(benchmark.to_json() + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(manifest.to_json() + "\n", encoding="utf-8")
    return manifest


def _read_fixture_artifact(path: Path) -> AcceleratorArtifact:
    """Check an artifact's identities, raw evidence, and bundled wheel."""
    data: Any = json.loads(
        (path / "manifest.json").read_text(encoding="utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )
    if not isinstance(data, dict) or set(data) != {
        item.name for item in fields(AcceleratorArtifact)
    } | {"content_sha256"}:
        raise ValueError("unexpected artifact fields")
    digest = data.pop("content_sha256")
    if (
        not isinstance(digest, str)
        or hashlib.sha256(_json(data).encode()).hexdigest() != digest
    ):
        raise ValueError("artifact manifest digest mismatch")
    baseline_data = data["baseline"]
    if not isinstance(baseline_data, dict) or set(baseline_data) != {
        item.name for item in fields(ReferenceBaseline)
    }:
        raise ValueError("unexpected baseline fields")
    provenance_data = baseline_data["provenance"]
    if not isinstance(provenance_data, dict) or set(provenance_data) != {
        item.name for item in fields(ExecutionProvenance)
    }:
        raise ValueError("unexpected baseline provenance")
    gpu = provenance_data["gpu"]
    if gpu is not None:
        if not isinstance(gpu, dict) or set(gpu) != {
            item.name for item in fields(GPUProvenance)
        }:
            raise ValueError("unexpected GPU provenance")
        provenance_data["gpu"] = GPUProvenance(**gpu)
    baseline_data["provenance"] = ExecutionProvenance(**provenance_data)
    baseline_data["times_ns"] = tuple(baseline_data["times_ns"])
    baseline = ReferenceBaseline(**baseline_data)
    data["reference"] = ImplementationIdentity(**data["reference"])
    data["candidate"] = ImplementationIdentity(**data["candidate"])
    data["baseline"] = baseline
    data["reproduce"] = tuple(data["reproduce"])
    manifest = AcceleratorArtifact(**data)
    if (
        manifest.schema_version != 1
        or manifest.fixture is not True
        or manifest.accelerator_id != orbit.DESCRIPTOR.id
        or manifest.accelerator_version != orbit.DESCRIPTOR.version
        or manifest.reference != orbit.DESCRIPTOR.reference
        or manifest.candidate != orbit.NUMPY
        or manifest.input_domain != orbit.DESCRIPTOR.input_contract
        or manifest.case_id not in {item.id for item in orbit.DESCRIPTOR.cases}
        or manifest.reference_invocation
        != f"raddle.orbit.reference(raddle.orbit.case({manifest.case_id!r}))"
        or baseline.invocation != manifest.reference_invocation
        or manifest.candidate_invocation
        != f"raddle.orbit.accelerated(raddle.orbit.case({manifest.case_id!r}))"
        or manifest.validation_method != VALIDATION_METHOD
        or manifest.benchmark_file != "benchmark.json"
        or manifest.reproduce
        != _reproduce(
            manifest.case_id, manifest.wheel_file, baseline.repeat, baseline.warmup
        )
        or baseline.clock != "perf_counter_ns"
        or type(baseline.repeat) is not int
        or baseline.repeat <= 0
        or type(baseline.warmup) is not int
        or baseline.warmup < 0
        or len(baseline.times_ns) != baseline.repeat
        or any(type(value) is not int or value <= 0 for value in baseline.times_ns)
        or baseline.median_ns != statistics.median(baseline.times_ns)
        or baseline.provenance.gpu is not None
    ):
        raise ValueError("invalid artifact manifest or baseline")
    for filename in (manifest.wheel_file, manifest.benchmark_file):
        if Path(filename).name != filename:
            raise ValueError("artifact files must be local")
    wheel = path / manifest.wheel_file
    receipt_path = path / manifest.benchmark_file
    if (
        _sha256(wheel) != manifest.wheel_sha256
        or _sha256(receipt_path) != manifest.benchmark_sha256
    ):
        raise ValueError("artifact file digest mismatch")
    _check_wheel(wheel, baseline.provenance.raddle_version)
    receipt = read_receipt(receipt_path)
    if (
        receipt["accelerator_id"] != manifest.accelerator_id
        or receipt["accelerator_version"] != manifest.accelerator_version
        or receipt["case_id"] != manifest.case_id
        or receipt["validation"]["reference"] != asdict(manifest.reference)
        or receipt["validation"]["candidate"] != asdict(manifest.candidate)
        or receipt["baseline"] != asdict(manifest.reference)
        or receipt["repeat"] != baseline.repeat
        or receipt["warmup"] != baseline.warmup
        or asdict(baseline.provenance) != receipt["provenance"] | {"gpu": None}
        or receipt["timing_scope"] != "end_to_end"
    ):
        raise ValueError("artifact and benchmark identities differ")
    stored_manifest = (path / "manifest.json").read_text(encoding="utf-8")
    if stored_manifest != manifest.to_json() + "\n":
        legacy_data = asdict(manifest)
        legacy_data.pop("precision", None)
        legacy_data["content_sha256"] = hashlib.sha256(
            _json(legacy_data).encode()
        ).hexdigest()
        if stored_manifest == _json(legacy_data) + "\n":
            return manifest
        raise ValueError("artifact manifest is not canonical JSON")
    return manifest


def _wheel_source(path: Path, member: str) -> bytes:
    if (
        Path(member).is_absolute()
        or ".." in Path(member).parts
        or not member.endswith(".py")
    ):
        raise ValueError("invalid candidate source member")
    try:
        with zipfile.ZipFile(path) as wheel:
            return wheel.read(member)
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise ValueError("candidate source missing from wheel") from error


def _external_candidate_wheel(
    raddle_wheel: Path,
    workload_wheel: Path,
    candidate_package: str,
    workload_package: str,
) -> Path:
    if candidate_package == workload_package:
        return workload_wheel
    if candidate_package == "raddle":
        return raddle_wheel
    raise ValueError("candidate package must be in a bundled wheel")


def _check_candidate_wheel(path: Path, name: str, version: str) -> None:
    if path.suffix != ".whl":
        raise ValueError("candidate must be a wheel")
    try:
        with zipfile.ZipFile(path) as wheel:
            metadata = next(
                item
                for item in wheel.namelist()
                if item.endswith(".dist-info/METADATA")
            )
            details = Parser().parsestr(wheel.read(metadata).decode("utf-8"))
    except (
        OSError,
        ValueError,
        KeyError,
        StopIteration,
        UnicodeError,
        zipfile.BadZipFile,
    ) as error:
        raise ValueError("invalid candidate wheel") from error
    if (
        details.get("Name", "").lower().replace("_", "-") != name
        or details.get("Version") != version
    ):
        raise ValueError("candidate wheel identity mismatch")


def create_external_artifact(
    *,
    descriptor: AcceleratorDescriptor,
    case: CaseDescriptor | ExternalCaseDescriptor,
    reference: Callable[[], object],
    candidate: Callable[[], object],
    validate: Callable[[object, object], ValidationReceipt],
    inputs_json: str,
    reference_source_url: str,
    reference_source_revision: str,
    reference_invocation: str,
    candidate_invocation: str,
    validation_method: str,
    profile: dict[str, object],
    dependencies: dict[str, str],
    raddle_wheel: Path,
    workload_wheel: Path,
    candidate_package: str,
    candidate_package_version: str,
    candidate_source_member: str,
    workload_package: str,
    workload_package_version: str,
    lock_file: Path,
    output: Path,
    repeat: int = 3,
    warmup: int = 0,
    precision: str = "float64",
    provenance: ExecutionProvenance | None = None,
    timing_scope: TimingScope = TimingScope.END_TO_END,
    reproduce: tuple[str, ...] | None = None,
) -> ExternalAcceleratorArtifact:
    """Run a supplied external case; only validated results become evidence."""
    if output.exists():
        raise ValueError(f"artifact output already exists: {output}")
    if type(repeat) is not int or repeat <= 0 or type(warmup) is not int or warmup < 0:
        raise ValueError("repeat must be positive and warmup nonnegative")
    if case not in descriptor.cases or descriptor.reference == descriptor.candidate:
        raise ValueError("external case or implementation identity mismatch")
    if (
        not reference_source_revision.startswith("git:")
        or len(reference_source_revision) != 44
    ):
        raise ValueError("reference must name a full Git revision")
    case_data = asdict(case)
    inputs: Any = json.loads(inputs_json)
    if not isinstance(inputs, dict) or inputs.get("case") != case_data:
        raise ValueError("inputs must identify the canonical case")
    inputs_bytes = (_json(inputs) + "\n").encode("utf-8")
    _check_wheel(raddle_wheel, __version__)
    _check_runtime_matches_wheel(raddle_wheel)
    candidate_wheel = _external_candidate_wheel(
        raddle_wheel, workload_wheel, candidate_package, workload_package
    )
    _check_candidate_wheel(
        candidate_wheel, candidate_package, candidate_package_version
    )
    _check_candidate_wheel(workload_wheel, workload_package, workload_package_version)
    source = _wheel_source(candidate_wheel, candidate_source_member)
    candidate_revision = "sha256:" + hashlib.sha256(source).hexdigest()
    provenance = provenance or ExecutionProvenance.current()
    for _ in range(warmup):
        reference()
    baseline_times: list[int] = []
    expected: object | None = None
    for _ in range(repeat):
        start = time.perf_counter_ns()
        expected = reference()
        baseline_times.append(time.perf_counter_ns() - start)
    if expected is None:
        raise ValueError("reference returned no result")
    baseline = ReferenceBaseline(
        invocation=reference_invocation,
        clock="perf_counter_ns",
        warmup=warmup,
        repeat=repeat,
        times_ns=tuple(baseline_times),
        median_ns=statistics.median(baseline_times),
        provenance=provenance,
    )
    validation = validate(expected, candidate())
    if (
        validation.status != "matched"
        or validation.accelerator_id != descriptor.id
        or validation.accelerator_version != descriptor.version
        or validation.case_id != case.id
        or validation.reference != descriptor.reference
        or validation.candidate != descriptor.candidate
        or validation.policy != descriptor.validation_policy
    ):
        raise ValueError("candidate failed reference validation; no artifact created")
    for _ in range(warmup):
        reference()
        candidate()
    paired_reference: list[int] = []
    paired_candidate: list[int] = []
    for _ in range(repeat):
        start = time.perf_counter_ns()
        reference()
        paired_reference.append(time.perf_counter_ns() - start)
        start = time.perf_counter_ns()
        candidate()
        paired_candidate.append(time.perf_counter_ns() - start)
    median_reference = statistics.median(paired_reference)
    median_candidate = statistics.median(paired_candidate)
    benchmark = BenchmarkReceipt(
        schema_version=3,
        accelerator_id=descriptor.id,
        accelerator_version=descriptor.version,
        case_id=case.id,
        workload=case_data,
        validation=validation,
        clock="perf_counter_ns",
        timing_scope=timing_scope,
        setup_included=False,
        host_device_transfers=(
            TransferInclusion.NOT_APPLICABLE
            if provenance.gpu is None
            else (
                TransferInclusion.INCLUDED
                if timing_scope is TimingScope.END_TO_END
                else TransferInclusion.EXCLUDED
            )
        ),
        baseline=descriptor.reference,
        baseline_synchronization=Synchronization.SYNCHRONOUS,
        candidate_synchronization=(
            Synchronization.CUDA_STREAM
            if provenance.gpu is not None
            else Synchronization.SYNCHRONOUS
        ),
        warmup=warmup,
        repeat=repeat,
        baseline_times_ns=tuple(paired_reference),
        candidate_times_ns=tuple(paired_candidate),
        median_baseline_ns=median_reference,
        median_candidate_ns=median_candidate,
        speedup=median_reference / median_candidate,
        provenance=provenance,
    )
    command = (
        f"uvx --from {shlex.quote('./' + workload_wheel.name)} "
        f"--with {shlex.quote('./' + raddle_wheel.name)} raddle-ssapy artifact "
        f"--case {shlex.quote(case.id)} "
        f"--raddle-wheel {shlex.quote('./' + raddle_wheel.name)} "
        f"--workload-wheel {shlex.quote('./' + workload_wheel.name)} "
        f"--lock {shlex.quote('./' + lock_file.name)} "
        f"--output ./reproduced --repeat {repeat} --warmup {warmup}"
    )
    manifest = ExternalAcceleratorArtifact(
        schema_version=2,
        fixture=False,
        accelerator_id=descriptor.id,
        accelerator_version=descriptor.version,
        case_id=case.id,
        workload=case_data,
        reference=descriptor.reference,
        candidate=descriptor.candidate,
        policy=descriptor.validation_policy,
        reference_invocation=reference_invocation,
        candidate_invocation=candidate_invocation,
        input_domain=descriptor.input_contract,
        output_contract=descriptor.output_contract,
        validation_method=validation_method,
        reference_source_url=reference_source_url,
        reference_source_revision=reference_source_revision,
        candidate_source_revision=candidate_revision,
        candidate_source_member=candidate_source_member,
        candidate_package_name=candidate_package,
        candidate_package_version=candidate_package_version,
        workload_package_name=workload_package,
        workload_package_version=workload_package_version,
        dependencies=dependencies,
        profile=profile,
        baseline=baseline,
        inputs_file="inputs.json",
        inputs_sha256=hashlib.sha256(inputs_bytes).hexdigest(),
        lock_file=lock_file.name,
        lock_sha256=_sha256(lock_file),
        benchmark_file="benchmark.json",
        benchmark_sha256=hashlib.sha256(
            (benchmark.to_json() + "\n").encode()
        ).hexdigest(),
        wheel_file=raddle_wheel.name,
        wheel_sha256=_sha256(raddle_wheel),
        workload_wheel_file=workload_wheel.name,
        workload_wheel_sha256=_sha256(workload_wheel),
        reproduce=reproduce or (command,),
        precision=precision,
    )
    output.mkdir(parents=True)
    for source_path in (raddle_wheel, workload_wheel, lock_file):
        shutil.copyfile(source_path, output / source_path.name)
    (output / "inputs.json").write_bytes(inputs_bytes)
    (output / "benchmark.json").write_text(benchmark.to_json() + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(manifest.to_json() + "\n", encoding="utf-8")
    return manifest


def _read_external_artifact(path: Path) -> ExternalAcceleratorArtifact:
    data: Any = json.loads(
        (path / "manifest.json").read_text(encoding="utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )
    fields_now = {item.name for item in fields(ExternalAcceleratorArtifact)}
    if not isinstance(data, dict) or set(data) not in (
        fields_now | {"content_sha256"},
        (fields_now - {"precision"}) | {"content_sha256"},
    ):
        raise ValueError("unexpected external artifact fields")
    digest = data.pop("content_sha256")
    if (
        not isinstance(digest, str)
        or hashlib.sha256(_json(data).encode()).hexdigest() != digest
    ):
        raise ValueError("artifact manifest digest mismatch")
    precision_was_recorded = "precision" in data
    data.setdefault("precision", "float64")
    baseline_data = data["baseline"]
    if not isinstance(baseline_data, dict) or set(baseline_data) != {
        item.name for item in fields(ReferenceBaseline)
    }:
        raise ValueError("unexpected external baseline fields")
    provenance_data = baseline_data["provenance"]
    if not isinstance(provenance_data, dict) or set(provenance_data) != {
        item.name for item in fields(ExecutionProvenance)
    }:
        raise ValueError("unexpected external baseline provenance")
    if provenance_data["gpu"] is not None:
        gpu_fields = {item.name for item in fields(GPUProvenance)}
        if not isinstance(provenance_data["gpu"], dict) or set(
            provenance_data["gpu"]
        ) not in (gpu_fields, gpu_fields - {"backend", "backend_version"}):
            raise ValueError("unexpected external GPU provenance")
        provenance_data["gpu"] = GPUProvenance(**provenance_data["gpu"])
    baseline_data["provenance"] = ExecutionProvenance(**baseline_data["provenance"])
    baseline_data["times_ns"] = tuple(baseline_data["times_ns"])
    data["baseline"] = ReferenceBaseline(**baseline_data)
    data["reference"] = ImplementationIdentity(**data["reference"])
    data["candidate"] = ImplementationIdentity(**data["candidate"])
    data["policy"] = ValidationPolicy(**data["policy"])
    data["reproduce"] = tuple(data["reproduce"])
    manifest = ExternalAcceleratorArtifact(**data)
    if (
        manifest.schema_version != 2
        or manifest.fixture is not False
        or manifest.case_id != manifest.workload.get("id")
        or manifest.baseline.invocation != manifest.reference_invocation
        or manifest.baseline.clock != "perf_counter_ns"
        or manifest.baseline.repeat <= 0
        or manifest.baseline.warmup < 0
        or len(manifest.baseline.times_ns) != manifest.baseline.repeat
        or any(
            type(value) is not int or value <= 0 for value in manifest.baseline.times_ns
        )
        or manifest.baseline.median_ns != statistics.median(manifest.baseline.times_ns)
        or not manifest.reference_source_revision.startswith("git:")
        or len(manifest.reference_source_revision) != 44
        or not manifest.candidate_source_revision.startswith("sha256:")
        or not manifest.profile.get("top")
        or manifest.dependencies.get(manifest.candidate_package_name)
        != manifest.candidate_package_version
        or manifest.dependencies.get(manifest.workload_package_name)
        != manifest.workload_package_version
        or manifest.reference.version not in manifest.dependencies.values()
        or any(
            not isinstance(name, str)
            or not isinstance(version, str)
            or not name
            or not version
            for name, version in manifest.dependencies.items()
        )
    ):
        raise ValueError("invalid external artifact manifest")
    for filename in (
        manifest.inputs_file,
        manifest.lock_file,
        manifest.benchmark_file,
        manifest.wheel_file,
        manifest.workload_wheel_file,
    ):
        if Path(filename).name != filename:
            raise ValueError("artifact files must be local")
    for filename, digest in (
        (manifest.inputs_file, manifest.inputs_sha256),
        (manifest.lock_file, manifest.lock_sha256),
        (manifest.benchmark_file, manifest.benchmark_sha256),
        (manifest.wheel_file, manifest.wheel_sha256),
        (manifest.workload_wheel_file, manifest.workload_wheel_sha256),
    ):
        if _sha256(path / filename) != digest:
            raise ValueError("artifact file digest mismatch")
    _check_wheel(
        path / manifest.wheel_file, manifest.baseline.provenance.raddle_version
    )
    candidate_wheel = _external_candidate_wheel(
        path / manifest.wheel_file,
        path / manifest.workload_wheel_file,
        manifest.candidate_package_name,
        manifest.workload_package_name,
    )
    _check_candidate_wheel(
        candidate_wheel,
        manifest.candidate_package_name,
        manifest.candidate_package_version,
    )
    if (
        "sha256:"
        + hashlib.sha256(
            _wheel_source(candidate_wheel, manifest.candidate_source_member)
        ).hexdigest()
        != manifest.candidate_source_revision
    ):
        raise ValueError("candidate source revision mismatch")
    _check_candidate_wheel(
        path / manifest.workload_wheel_file,
        manifest.workload_package_name,
        manifest.workload_package_version,
    )
    inputs: Any = json.loads((path / manifest.inputs_file).read_text(encoding="utf-8"))
    if not isinstance(inputs, dict) or inputs.get("case") != manifest.workload:
        raise ValueError("artifact inputs differ from case")
    workload = manifest.workload
    case_id = workload.get("id")
    if not isinstance(case_id, str):
        raise ValueError("invalid external case descriptor")
    if set(workload) == {"id", "trajectories", "mu", "dt", "steps"}:
        trajectories = workload.get("trajectories")
        mu = workload.get("mu")
        dt = workload.get("dt")
        steps = workload.get("steps")
        if (
            type(trajectories) is not int
            or not isinstance(mu, (float, int))
            or isinstance(mu, bool)
            or not isinstance(dt, (float, int))
            or isinstance(dt, bool)
            or type(steps) is not int
        ):
            raise ValueError("invalid external case descriptor")
        case: CaseDescriptor | ExternalCaseDescriptor = CaseDescriptor(
            case_id, trajectories, float(mu), float(dt), steps
        )
    elif set(workload) == {"id", "parameters"} and isinstance(
        workload.get("parameters"), dict
    ):
        case = ExternalCaseDescriptor(
            case_id, cast(dict[str, object], workload["parameters"])
        )
    else:
        raise ValueError("invalid external case descriptor")
    if (
        manifest.workload.get("id") != manifest.case_id
        or not manifest.reference_invocation
        or not manifest.candidate_invocation
        or not manifest.validation_method
        or not manifest.reference_source_url.startswith("https://")
        or not manifest.candidate_source_member.endswith(".py")
        or manifest.baseline.provenance.raddle_version
        != manifest.dependencies.get("raddle")
    ):
        raise ValueError("invalid external workload identity")
    descriptor = AcceleratorDescriptor(
        id=manifest.accelerator_id,
        version=manifest.accelerator_version,
        name="External workload",
        reference=manifest.reference,
        candidates=(manifest.candidate,),
        input_contract=manifest.input_domain,
        output_contract=manifest.output_contract,
        precision=manifest.precision,
        supported_environment="recorded in artifact",
        validation_policy=manifest.policy,
        cases=(case,),
    )
    receipt = read_receipt(path / manifest.benchmark_file, descriptor)
    if (
        receipt["validation"]["reference"] != asdict(manifest.reference)
        or receipt["validation"]["candidate"] != asdict(manifest.candidate)
        or receipt["repeat"] != manifest.baseline.repeat
        or receipt["warmup"] != manifest.baseline.warmup
        or receipt["provenance"] != asdict(manifest.baseline.provenance)
        or receipt["timing_scope"] not in ("end_to_end", "compute_only")
    ):
        raise ValueError("artifact and benchmark identities differ")
    canonical_manifest = json.loads(manifest.to_json())
    if not precision_was_recorded:
        canonical_manifest.pop("precision")
        canonical_manifest.pop("content_sha256")
        canonical_manifest["content_sha256"] = hashlib.sha256(
            _json(canonical_manifest).encode()
        ).hexdigest()
    if (path / "manifest.json").read_text(encoding="utf-8") != _json(
        canonical_manifest
    ) + "\n":
        raise ValueError("artifact manifest is not canonical JSON")
    return manifest


def read_artifact(path: Path) -> AcceleratorArtifact | ExternalAcceleratorArtifact:
    """Read either the unchanged fixture schema or a checked external bundle."""
    header: Any = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(header, dict):
        raise ValueError("invalid artifact manifest")
    if header.get("schema_version") == 1:
        return _read_fixture_artifact(path)
    if header.get("schema_version") == 2:
        return _read_external_artifact(path)
    raise ValueError("unsupported artifact schema")
