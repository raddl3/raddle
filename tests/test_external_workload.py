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
    experiment = rows[-2]["record"]
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


def test_two_loop_fixture(tmp_path: Path) -> None:
    """Scripted selection scores exercise lineage, never performance claims."""
    root = Path(__file__).resolve().parents[1]
    wheels = tmp_path / "wheels"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(wheels)],
        cwd=root,
        check=True,
        capture_output=True,
    )
    script = r"""
import hashlib
import json
import shutil
import sys
from dataclasses import replace
from pathlib import Path
import external_workload.__main__ as demo
from raddle.artifact import read_artifact

root, wheel = map(Path, sys.argv[1:])
# Execute the real callbacks, but use deterministic fixture scores for selection.
# Artifact creation uses its own real clock and validation, unaffected by this stub.
real_measure = demo.measure
scores = iter([100.0, 50.0, 40.0, 20.0])
calls = []
def fixture_measure(call):
    evidence = real_measure(call)
    calls.append(evidence)
    evidence = dict(evidence)
    evidence['median_ns'] = next(scores)
    evidence['fixture_score_only'] = True
    return evidence
demo.measure = fixture_measure
first = demo.run(root / 'loop-001', wheel, approve_target=True)
adopted = root / 'adopted.py'
shutil.copyfile(first.incumbent_source(), adopted)
# A distinct implementation in loop 2, still exact against the original reference.
source = root / 'multiply.py'
source.write_text(
    "import numpy as np\ndef run(size):\n"
    "    a = np.arange(size, dtype=np.float64)\n    return np.multiply(a, a)\n"
)
parent_files = {
    p: p.read_bytes() for p in first.ledger.parent.rglob('*') if p.is_file()
}
args = dict(campaign_id='declined', budget=3, target=first.contract.target,
    adopted_source=adopted, parent_artifact=first.ledger.parent / 'artifacts',
    baseline_score=40.0, baseline_evidence={}, profile_evidence={})
for changes, message in [
    ({'approved': False}, 'approval'),
    ({'approved': True,
      'target': replace(first.contract.target, objective='throughput')}, 'target'),
    ({'approved': True, 'campaign_id': first.contract.campaign_id}, 'new campaign'),
    ({'approved': True, 'adopted_source': source}, 'adopted source'),
]:
    try:
        first.next_loop(root / 'declined' / 'forge.jsonl', **(args | changes))
    except ValueError as error:
        assert message in str(error)
    else:
        raise AssertionError('invalid loop accepted')
    assert not (root / 'declined').exists()
second = demo.run(root / 'loop-002', wheel, approve_target=True, parent=first,
    approve_loop=True, adopted_source=adopted, candidate_source=source)
assert all(p.read_bytes() == content for p, content in parent_files.items())
assert len(calls) == 4  # Both baseline and candidate callbacks executed in each loop.
a, b = first.status(), second.status()
assert a['remaining_budget'] == b['remaining_budget'] == 0
assert b['attempts_used'] == 1 and b['contract']['budget'] == 1
assert b['baseline_id'] == a['incumbent']['experiment_id']
assert b['baseline_score'] == 40.0 != a['incumbent']['score']
assert b['profile'] != a['profile']
assert second.contract.reference_identity == first.contract.reference_identity
assert second.contract.target == first.contract.target
lineage = b['contract']['lineage']
assert lineage['loop_number'] == 2
assert lineage['parent_campaign_id'] == first.contract.campaign_id
parent_manifest = first.ledger.parent / 'artifacts/manifest.json'
assert lineage['parent_artifact_sha256'] == hashlib.sha256(
    parent_manifest.read_bytes()
).hexdigest()
assert lineage['baseline_source_sha256'] == hashlib.sha256(
    adopted.read_bytes()
).hexdigest()
assert (b['experiments'][0]['validation']['reference']
    == a['experiments'][0]['validation']['reference'])
artifact = read_artifact(second.ledger.parent / 'artifacts')
assert artifact.reference == read_artifact(first.ledger.parent / 'artifacts').reference
assert (artifact.candidate_source_revision
    == 'sha256:' + b['incumbent']['candidate_source_hash'])
assert (b['incumbent']['candidate_source_hash']
    != a['incumbent']['candidate_source_hash'])
rows = [json.loads(line) for line in second.ledger.read_text().splitlines()]
assert rows[-1]['event'] == 'forge-artifact'
assert rows[-1]['record']['campaign_id'] == second.contract.campaign_id
third = second.next_loop(root / 'loop-003/forge.jsonl', campaign_id='loop-3',
    budget=3, target=second.contract.target, approved=True,
    adopted_source=second.incumbent_source(),
    parent_artifact=second.ledger.parent / 'artifacts',
    baseline_score=18.0, baseline_evidence={'fixture': True},
    profile_evidence={'fixture': True})
assert third.status()['remaining_budget'] == 3
assert third.status()['attempts_used'] == 0
assert third.contract.lineage.loop_number == 3
"""
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
            "-c",
            script,
            str(tmp_path),
            str(next(wheels.glob("raddle-*.whl"))),
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
