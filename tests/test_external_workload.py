"""Check the documentation example through its own locked environment."""

import json
import shlex
import subprocess
from pathlib import Path

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
    output = tmp_path / "campaign"
    subprocess.run(
        [
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
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )
    rows = [
        json.loads(line) for line in (output / "ledger.jsonl").read_text().splitlines()
    ]
    experiment = rows[-1]["record"]
    assert experiment["accepted"] is True
    assert experiment["validation"]["status"] == "matched"
    artifact = read_artifact(output / "artifact")
    assert isinstance(artifact, ExternalAcceleratorArtifact)
    assert (
        artifact.candidate_source_revision
        == "sha256:" + experiment["candidate_source_hash"]
    )
    assert artifact.baseline.median_ns > 0
    reproduced = subprocess.run(
        shlex.split(artifact.reproduce[0]),
        cwd=output / "artifact",
        check=True,
        capture_output=True,
        text=True,
    )
    assert '"status":"matched"' in reproduced.stdout
    assert "times_ns" in reproduced.stdout
