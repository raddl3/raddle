"""Check the documentation example through its own locked environment."""

import hashlib
import json
import shlex
import subprocess
from pathlib import Path
from zipfile import ZipFile

from raddle.artifact import read_artifact
from raddle.contracts import ExternalAcceleratorArtifact


def test_complete_external_integration(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    wheels = tmp_path / "wheels"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(wheels)],
        cwd=root,
        check=True,
        capture_output=True,
    )
    with ZipFile(next(wheels.glob("raddle-*.whl"))) as wheel:
        for name in (
            "scoping",
            "opportunities",
            "ml-inference",
            "external-workload",
            "evaluation",
            "artifacts",
        ):
            assert (
                f"raddle/skills/raddle-accelerate/references/{name}.md"
                in wheel.namelist()
            )
    output = tmp_path / "campaign"
    command = [
        "uv",
        "run",
        "--project",
        "examples/external-workload",
        "--python",
        "3.12",
        "--frozen",
        "python",
        "-m",
        "external_workload",
        str(output),
        str(next(wheels.glob("raddle-*.whl"))),
    ]
    proposal = subprocess.run(command, cwd=root, capture_output=True, text=True)
    assert proposal.returncode != 0
    assert "Is this the workload you want accelerated?" in proposal.stdout
    assert not output.exists()
    subprocess.run(
        command + ["--approve-target"], cwd=root, check=True, capture_output=True
    )
    rows = [
        json.loads(line) for line in (output / "forge.jsonl").read_text().splitlines()
    ]
    contract = rows[0]["record"]["contract"]
    assert contract["target"]["target_id"] == "external-square.v1"
    canonical = json.dumps(contract["target"], sort_keys=True, separators=(",", ":"))
    assert contract["target_sha256"] == hashlib.sha256(canonical.encode()).hexdigest()
    experiment = rows[-1]["record"]
    assert experiment["accepted"] is True
    assert experiment["validation"]["status"] == "matched"
    artifact = read_artifact(output / "artifacts")
    assert isinstance(artifact, ExternalAcceleratorArtifact)
    assert (
        artifact.candidate_source_revision
        == "sha256:" + experiment["candidate_source_hash"]
    )
    assert artifact.baseline.median_ns > 0
    reproduced = subprocess.run(
        shlex.split(artifact.reproduce[0]),
        cwd=output / "artifacts",
        check=True,
        capture_output=True,
        text=True,
    )
    assert '"status":"matched"' in reproduced.stdout
    assert "times_ns" in reproduced.stdout
