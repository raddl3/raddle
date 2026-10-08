"""Bounded, read-only readiness checks; no application commands or remediation."""

import hashlib
import json
import os
import platform
import shutil
import subprocess  # nosec B404 # intentional native runtime/probe execution
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from raddle import __version__
from raddle.agent import read_config


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


def accessible(path: Path) -> bool:
    while not path.exists() and path != path.parent:
        path = path.parent
    return path.is_dir() and os.access(path, os.W_OK | os.X_OK)


def run_probe(argv: list[str], root: Path) -> str | None:
    try:
        result = subprocess.run(  # nosec B603 # fixed flags, argv list, no shell
            argv, cwd=root, capture_output=True, text=True, timeout=15, check=False
        )
        return result.stdout if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def readiness(
    root: Path,
    *,
    workload_approved: bool = False,
    device: str | None = None,
    framework: str | None = None,
    python: Path | None = None,
    artifacts: tuple[str, ...] = (),
    tools: tuple[str, ...] = (),
    scratch: Path | None = None,
    min_free_bytes: int = 0,
) -> list[Check]:
    root = root.resolve()
    if (
        device or framework or artifacts or python or scratch or min_free_bytes
    ) and not workload_approved:
        raise ValueError(
            "workload-specific checks require --workload-approved after target approval"
        )
    if framework and device is None:
        raise ValueError("framework checks require the approved --device")
    if min_free_bytes < 0:
        raise ValueError("minimum free bytes must be nonnegative")
    checks = [
        Check("raddle", "PASS", __version__),
        Check(
            "python",
            "PASS" if sys.version_info >= (3, 12) else "BLOCKED",
            "Raddle requires Python 3.12+",
        ),
        Check(
            "os",
            "PASS" if platform.system() in ("Linux", "Darwin", "Windows") else "WARN",
            platform.system(),
        ),
        Check(
            "workspace",
            "PASS" if root.is_dir() else "BLOCKED",
            "project directory must exist",
        ),
    ]
    if not root.is_dir():
        return checks
    git = shutil.which("git")
    worktree = (
        run_probe([git, "rev-parse", "--is-inside-work-tree"], root)
        if git and (root / ".git").exists()
        else None
    )
    checks.append(
        Check(
            "repository",
            "PASS" if worktree and worktree.strip() == "true" else "WARN",
            "Git worktree verified"
            if worktree and worktree.strip() == "true"
            else "Agree candidate isolation before edits; Git worktree not verified",
        )
    )
    for name, path in [
        ("workspace permissions", root),
        ("campaign permissions", root / ".raddle/campaigns"),
    ]:
        checks.append(
            Check(
                name,
                "PASS" if accessible(path) else "BLOCKED",
                "access flags allow writing; actual writes were not attempted"
                if accessible(path)
                else "choose a writable location or approve permission repair",
            )
        )
    try:
        config = read_config(root)
        folder = (
            root
            / (".agents" if config["agent"] == "codex" else ".claude")
            / "skills/raddle-accelerate/SKILL.md"
        )
        checks.append(
            Check(
                "agent configuration",
                "PASS"
                if folder.is_file() and folder.with_name("KICKOFF.md").is_file()
                else "BLOCKED",
                "launch configuration and runtime interface verified"
                if folder.is_file() and folder.with_name("KICKOFF.md").is_file()
                else "run raddle init to install the skill",
            )
        )
    except ValueError as error:
        checks.append(Check("agent configuration", "BLOCKED", str(error)))
    checks.append(
        Check(
            "agent authentication/backend",
            "NOT CHECKED",
            (
                "inherited from runtime; verify inside the agent, no "
                "credentials inspected or API call made"
            ),
        )
    )
    if os.environ.get("VIRTUAL_ENV") and os.environ.get("CONDA_PREFIX"):
        checks.append(
            Check(
                "environment",
                "WARN",
                (
                    "both virtualenv and Conda are active; select the "
                    "approved workload interpreter explicitly"
                ),
            )
        )
    else:
        checks.append(
            Check(
                "environment",
                "PASS",
                "no simultaneous virtualenv/Conda activation detected",
            )
        )
    for tool in tools:
        if not tool or tool.startswith("-") or "/" in tool or "\\" in tool:
            raise ValueError("tools must be executable names, not commands or paths")
        checks.append(
            Check(
                "tool " + tool,
                "PASS" if shutil.which(tool) else "BLOCKED",
                "found on PATH"
                if shutil.which(tool)
                else "install the required tool only after approval",
            )
        )
    if not workload_approved:
        checks.append(
            Check(
                "workload readiness",
                "NOT CHECKED",
                "approve a concrete target before requesting workload checks",
            )
        )
        return checks
    checks.append(
        Check(
            "CPU",
            "PASS" if os.cpu_count() else "NOT CHECKED",
            "logical CPUs detected; workload affinity/throughput not verified",
        )
    )
    scratch = scratch or root / ".raddle/campaigns"
    checks.append(
        Check(
            "scratch permissions",
            "PASS" if accessible(scratch) else "BLOCKED",
            "access flags checked without creating files",
        )
    )
    existing = scratch
    while not existing.exists():
        existing = existing.parent
    free = shutil.disk_usage(existing).free
    checks.append(
        Check(
            "scratch storage",
            "PASS"
            if free >= min_free_bytes and min_free_bytes
            else "BLOCKED"
            if free < min_free_bytes
            else "NOT CHECKED",
            f"{free} bytes free; required {min_free_bytes} bytes"
            if min_free_bytes
            else (
                "free space measured; supply --min-free-bytes for workload requirement"
            ),
        )
    )
    for artifact in artifacts:
        name, separator, digest = artifact.rpartition("=")
        if (
            not separator
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError("artifact must be PATH=SHA256 (lowercase hex)")
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError("artifact is outside the approved project boundary")
        try:
            with path.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            status = "PASS" if actual == digest else "BLOCKED"
        except OSError:
            status = "BLOCKED"
        checks.append(
            Check(
                "artifact " + name,
                status,
                "identity matches"
                if status == "PASS"
                else (
                    "missing, unreadable or changed; locate the approved "
                    "artifact, do not download automatically"
                ),
            )
        )
    if not artifacts:
        checks.append(
            Check(
                "artifact identities",
                "NOT CHECKED",
                "no approved artifacts specified; omit for workloads without artifacts",
            )
        )
    if device and device != "cpu":
        if not device.startswith("cuda:") or not device[5:].isdigit():
            raise ValueError("device must be cpu or cuda:INDEX")
        binary = shutil.which("nvidia-smi")
        output = (
            run_probe(
                [
                    binary,
                    "-i",
                    device[5:],
                    "--query-gpu=index",
                    "--format=csv,noheader",
                ],
                root,
            )
            if binary
            else None
        )
        checks.append(
            Check(
                "GPU driver",
                "PASS" if output and output.strip() else "BLOCKED",
                (
                    "selected GPU visible to driver; framework visibility "
                    "checked separately"
                )
                if output and output.strip()
                else (
                    "selected GPU unavailable; use approved CPU compute or "
                    "repair GPU access with approval"
                ),
            )
        )
        checks.append(
            Check(
                "GPU contention",
                "NOT CHECKED",
                (
                    "driver visibility does not establish exclusive access; "
                    "inspect contention within approved scope"
                ),
            )
        )
    if framework:
        if framework not in ("torch", "onnxruntime", "cupy"):
            raise ValueError("supported framework probes: torch, onnxruntime, cupy")
        if python is None:
            checks.append(
                Check(
                    "framework",
                    "NOT CHECKED",
                    (
                        "supply --python PATH to the trusted workload "
                        "interpreter; tool environment is separate"
                    ),
                )
            )
        else:
            # Fixed isolated probes; no application commands or model loading.
            program = {
                "torch": (
                    'import json,torch; print(json.dumps({"available": '
                    'torch.cuda.is_available(), "count": '
                    "torch.cuda.device_count()}))"
                )
                if device and device != "cpu"
                else ('import json,torch; print(json.dumps({"imported": True}))'),
                "onnxruntime": (
                    "import json,onnxruntime as ort; "
                    'print(json.dumps({"providers": '
                    "ort.get_available_providers()}))"
                ),
                "cupy": (
                    'import json,cupy; print(json.dumps({"count": '
                    "cupy.cuda.runtime.getDeviceCount()}))"
                )
                if device and device != "cpu"
                else 'import json,cupy; print(json.dumps({"imported": True}))',
            }[framework]
            output = run_probe([str(python), "-I", "-B", "-c", program], root)
            try:
                result = json.loads(output or "null")
                if not isinstance(result, dict):
                    raise ValueError("invalid probe response")
                gpu = bool(device and device != "cpu")
                if framework == "onnxruntime":
                    provider = (
                        "CUDAExecutionProvider" if gpu else "CPUExecutionProvider"
                    )
                    available = provider in result.get("providers", [])
                else:
                    available = not gpu or (
                        result.get("count", 0) > int((device or "cuda:0")[5:])
                        and (framework != "torch" or result.get("available") is True)
                    )
                checks.append(
                    Check(
                        "framework",
                        "PASS" if available else "BLOCKED",
                        "import and requested device/provider discovery succeeded"
                        if available
                        else (
                            "requested device/provider unavailable in the workload "
                            "environment"
                        ),
                    )
                )
            except (ValueError, TypeError):
                checks.append(
                    Check(
                        "framework",
                        "BLOCKED",
                        (
                            "probe failed; verify interpreter and framework "
                            "dependencies without changing them automatically"
                        ),
                    )
                )
    else:
        checks.append(
            Check(
                "framework",
                "NOT CHECKED",
                "no framework specified; not required for plain CPU workloads",
            )
        )
    checks.append(
        Check(
            "workload execution",
            "NOT CHECKED",
            (
                "configuration, model loading, CUDA library execution "
                "and benchmark boundary require an approved "
                "workload-specific probe; no application command "
                "executed"
            ),
        )
    )
    return checks


def report(checks: list[Check], as_json: bool) -> int:
    blocked = any(check.status == "BLOCKED" for check in checks)
    if as_json:
        print(
            json.dumps(
                {"blocked": blocked, "checks": [asdict(c) for c in checks]}, indent=2
            )
        )
    else:
        for check in checks:
            print(f"{check.status:11} {check.name}: {check.detail}")
    return 1 if blocked else 0
