import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest

from raddle.forge import (
    AccelerationTarget,
    BenchmarkResult,
    ForgeCampaign,
    ForgeContract,
    LoopLineage,
)


def _campaign(
    tmp_path: Path, budget: int = 2, *, target: AccelerationTarget | None = None
) -> ForgeCampaign:
    return ForgeCampaign(
        tmp_path / "forge.jsonl",
        ForgeContract(
            "case.one", {"revision": "abc"}, {"size": 4}, {"atol": 0.0}, budget, target
        ),
        baseline_id="baseline",
        baseline_score=10.0,
        baseline_evidence={"samples": [10.0]},
        profile_evidence={"top": ["reference"]},
        event="phase-d",
    )


def _evaluate(
    campaign: ForgeCampaign,
    tmp_path: Path,
    name: str,
    *,
    validation: str = "matched",
    score: float = 5.0,
    benchmark_calls: list[str] | None = None,
) -> dict[str, object]:
    source = tmp_path / name
    source.write_text(f"candidate = {name!r}\n", encoding="utf-8")

    def benchmark(_candidate: object) -> BenchmarkResult:
        if benchmark_calls is not None:
            benchmark_calls.append(name)
        return BenchmarkResult({"samples": [score]}, score)

    result = campaign.evaluate(
        candidate_source=source,
        source_store=tmp_path / "sources",
        experiment_id=name,
        parent_experiment="baseline",
        metadata={"task_id": "case.one", "phase": "D"},
        build=lambda snapshot: (snapshot.read_text(), {"status": "passed"}),
        validate=lambda _candidate: {"status": validation},
        benchmark=benchmark,
    )
    return result.record


def test_forge_resumes_ledger_and_enforces_budget(tmp_path: Path) -> None:
    campaign = _campaign(tmp_path, budget=1)
    _evaluate(campaign, tmp_path, "candidate.py")
    resumed = _campaign(tmp_path, budget=1)
    state = resumed.status()
    assert state["attempts_used"] == 1
    assert state["remaining_budget"] == 0
    with pytest.raises(ValueError, match="budget"):
        _evaluate(resumed, tmp_path, "second.py")


def test_interrupted_experiment_resumes_once_under_same_id(tmp_path: Path) -> None:
    campaign = _campaign(tmp_path, budget=1, target=_target())
    source = tmp_path / "candidate.py"
    source.write_text("candidate = 1\n", encoding="utf-8")

    def interrupted(_snapshot: Path) -> tuple[object, object]:
        raise KeyboardInterrupt

    def evaluate(build: object) -> object:
        return campaign.evaluate(
            candidate_source=source,
            source_store=tmp_path / "sources",
            experiment_id="trial-1",
            parent_experiment="baseline",
            metadata={"task_id": "case.one"},
            build=build,  # type: ignore[arg-type]
            validate=lambda _candidate: {"status": "matched"},
            benchmark=lambda _candidate: BenchmarkResult({}, 1.0),
        )

    with pytest.raises(KeyboardInterrupt):
        evaluate(interrupted)
    original_ledger = (tmp_path / "forge.jsonl").read_bytes()

    resumed = _campaign(tmp_path, budget=1, target=_target())
    result = resumed.evaluate(
        candidate_source=source,
        source_store=tmp_path / "sources",
        experiment_id="trial-1",
        parent_experiment="baseline",
        metadata={"task_id": "case.one"},
        build=lambda _snapshot: (object(), {"status": "passed"}),
        validate=lambda _candidate: {"status": "matched"},
        benchmark=lambda _candidate: BenchmarkResult({}, 1.0),
    )
    assert result.record["accepted"] is True
    assert (tmp_path / "forge.jsonl").read_bytes().startswith(original_ledger)
    assert (tmp_path / "forge.jsonl").read_bytes().count(b'"status":"started"') == 2
    assert resumed.status()["attempts_used"] == 1
    assert resumed.status()["remaining_budget"] == 0


def test_resume_rejects_changed_source(tmp_path: Path) -> None:
    campaign = _campaign(tmp_path, budget=1)
    source = tmp_path / "candidate.py"
    source.write_text("candidate = 1\n", encoding="utf-8")

    def interrupted(_snapshot: Path) -> tuple[object, object]:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        campaign.evaluate(
            candidate_source=source,
            source_store=tmp_path / "sources",
            experiment_id="trial-1",
            parent_experiment="baseline",
            metadata={"task_id": "case.one"},
            build=interrupted,
            validate=lambda _candidate: {"status": "matched"},
            benchmark=lambda _candidate: BenchmarkResult({}, 1.0),
        )
    source.write_text("candidate = 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="resume identity"):
        _campaign(tmp_path, budget=1).evaluate(
            candidate_source=source,
            source_store=tmp_path / "sources",
            experiment_id="trial-1",
            parent_experiment="baseline",
            metadata={"task_id": "case.one"},
            build=lambda _snapshot: (object(), {}),
            validate=lambda _candidate: {"status": "matched"},
            benchmark=lambda _candidate: BenchmarkResult({}, 1.0),
        )


def test_completed_experiment_cannot_resume(tmp_path: Path) -> None:
    campaign = _campaign(tmp_path)
    _evaluate(campaign, tmp_path, "candidate.py")
    with pytest.raises(ValueError, match="already complete"):
        _evaluate(_campaign(tmp_path), tmp_path, "candidate.py")


def test_resumed_validation_failure_never_benchmarks(tmp_path: Path) -> None:
    campaign = _campaign(tmp_path, budget=1)
    source = tmp_path / "candidate.py"
    source.write_text("candidate = 1\n", encoding="utf-8")

    def interrupted(_snapshot: Path) -> tuple[object, object]:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        campaign.evaluate(
            candidate_source=source,
            source_store=tmp_path / "sources",
            experiment_id="trial-1",
            parent_experiment="baseline",
            metadata={"task_id": "case.one"},
            build=interrupted,
            validate=lambda _candidate: {"status": "matched"},
            benchmark=lambda _candidate: pytest.fail("benchmark must not run"),
        )
    result = _campaign(tmp_path, budget=1).evaluate(
        candidate_source=source,
        source_store=tmp_path / "sources",
        experiment_id="trial-1",
        parent_experiment="baseline",
        metadata={"task_id": "case.one"},
        build=lambda _snapshot: (object(), {"status": "passed"}),
        validate=lambda _candidate: {"status": "mismatched"},
        benchmark=lambda _candidate: pytest.fail("benchmark must not run"),
    )
    assert result.record["benchmark"] is None
    assert result.record["accepted"] is False


def test_candidate_snapshot_and_hash_are_persisted(tmp_path: Path) -> None:
    campaign = _campaign(tmp_path)
    record = _evaluate(campaign, tmp_path, "candidate.py")
    snapshot = tmp_path / str(record["candidate_snapshot"])
    assert (
        snapshot.read_text(encoding="utf-8") == (tmp_path / "candidate.py").read_text()
    )
    assert record["candidate_source_hash"]
    assert (
        record["candidate_source_revision"]
        == f"sha256:{record['candidate_source_hash']}"
    )


def test_failed_validation_never_calls_benchmark(tmp_path: Path) -> None:
    campaign = _campaign(tmp_path)
    calls: list[str] = []
    record = _evaluate(
        campaign, tmp_path, "bad.py", validation="mismatched", benchmark_calls=calls
    )
    assert calls == []
    assert record["benchmark"] is None
    assert record["accepted"] is False


def test_valid_candidate_can_become_incumbent(tmp_path: Path) -> None:
    campaign = _campaign(tmp_path)
    record = _evaluate(campaign, tmp_path, "fast.py", score=4.0)
    state = _campaign(tmp_path).status()
    assert record["accepted"] is True
    assert state["incumbent"]["experiment_id"] == "fast.py"
    assert state["incumbent"]["score"] == 4.0
    assert (
        campaign.incumbent_source()
        .read_text(encoding="utf-8")
        .startswith("candidate =")
    )


def _target() -> AccelerationTarget:
    return AccelerationTarget(
        "workload.one",
        "app.run(4)",
        "size=4",
        "warm latency",
        "run including allocation",
        "revision:abc",
        ("app.py:run",),
        ("legacy/",),
        "User approved workload.one",
        ("local CPU",),
    )


def _target_campaign(
    tmp_path: Path, target: AccelerationTarget | None
) -> ForgeCampaign:
    return ForgeCampaign(
        tmp_path / "forge.jsonl",
        ForgeContract(
            "case.one", {"revision": "abc"}, {"size": 4}, {"atol": 0.0}, 2, target
        ),
        baseline_id="baseline",
        baseline_score=10.0,
        baseline_evidence={"samples": [10.0]},
        profile_evidence={"top": ["reference"]},
        event="phase-d",
    )


def test_target_is_immutable_and_hashed(tmp_path: Path) -> None:
    target = _target()
    with pytest.raises(FrozenInstanceError):
        target.objective = "throughput"  # type: ignore[misc]
    with pytest.raises(TypeError):
        target.included_paths[0] = "legacy/"  # type: ignore[index]
    with pytest.raises(ValueError, match="tuple"):
        replace(target, included_paths=["app.py"])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="nonempty"):
        replace(target, approval="")
    campaign = _target_campaign(tmp_path, target)
    contract = campaign.status()["contract"]
    assert contract["target_sha256"] == target.sha256
    assert contract["target"]["excluded_paths"] == ["legacy/"]
    assert _json_target_hash(contract["target"]) == target.sha256


def _json_target_hash(target: object) -> str:
    return hashlib.sha256(
        json.dumps(target, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@pytest.mark.parametrize("field", list(AccelerationTarget.__dataclass_fields__))
def test_reopen_rejects_any_changed_target(tmp_path: Path, field: str) -> None:
    target = _target()
    _target_campaign(tmp_path, target)
    original = (tmp_path / "forge.jsonl").read_bytes()
    value = getattr(target, field)
    changes: dict[str, Any] = {
        field: (*value, "changed") if isinstance(value, tuple) else value + "changed"
    }
    changed = replace(target, **changes)
    with pytest.raises(ValueError, match="changed"):
        _target_campaign(tmp_path, changed)
    with pytest.raises(ValueError, match="changed"):
        _target_campaign(tmp_path, None)
    assert (tmp_path / "forge.jsonl").read_bytes() == original
    assert _target_campaign(tmp_path, target).status()["remaining_budget"] == 2


def test_open_campaign_rejects_replaced_target_and_nested_contract_mutation(
    tmp_path: Path,
) -> None:
    campaign = _target_campaign(tmp_path, _target())
    original = (tmp_path / "forge.jsonl").read_bytes()
    campaign.contract = replace(
        campaign.contract, target=replace(_target(), objective="throughput")
    )
    with pytest.raises(ValueError, match="changed"):
        _evaluate(campaign, tmp_path, "candidate.py")
    campaign = _target_campaign(tmp_path, _target())
    identity = campaign.contract.reference_identity
    assert isinstance(identity, dict)
    identity["revision"] = "changed"
    with pytest.raises(ValueError, match="changed"):
        campaign.status()
    assert (tmp_path / "forge.jsonl").read_bytes() == original


def test_historical_targetless_campaign_is_read_without_rewrite(tmp_path: Path) -> None:
    ledger = tmp_path / "forge.jsonl"
    record = {
        "campaign_id": "case.one",
        "contract": {
            "campaign_id": "case.one",
            "reference_identity": {"revision": "abc"},
            "case_identity": {"size": 4},
            "validation_policy": {"atol": 0.0},
            "budget": 2,
        },
        "baseline_id": "baseline",
        "baseline_score": 10.0,
        "baseline": {"samples": [10.0]},
        "profile": {"top": ["reference"]},
    }
    original = (
        json.dumps({"event": "forge-campaign", "record": record}) + "\n"
    ).encode()
    ledger.write_bytes(original)
    campaign = _campaign(tmp_path)
    assert campaign.status()["contract"] == record["contract"]
    assert ledger.read_bytes() == original
    with pytest.raises(ValueError, match="changed"):
        _target_campaign(tmp_path, _target())
    assert ledger.read_bytes() == original
    assert _evaluate(campaign, tmp_path, "candidate.py")["accepted"] is True
    assert ledger.read_bytes().startswith(original)


def test_target_bound_validation_still_gates_benchmark(tmp_path: Path) -> None:
    campaign = _target_campaign(tmp_path, _target())
    calls: list[str] = []
    record = _evaluate(
        campaign, tmp_path, "bad.py", validation="mismatched", benchmark_calls=calls
    )
    assert record["accepted"] is False
    assert record["benchmark"] is None
    assert calls == []
    assert _target_campaign(tmp_path, _target()).status()["attempts_used"] == 1


def test_later_loop_requires_an_accepted_incumbent(tmp_path: Path) -> None:
    campaign = _target_campaign(tmp_path, _target())
    original = campaign.ledger.read_bytes()
    with pytest.raises(ValueError, match="baseline is still"):
        campaign.next_loop(
            tmp_path / "next/forge.jsonl",
            campaign_id="next",
            budget=3,
            target=_target(),
            approved=True,
            adopted_source=tmp_path / "missing.py",
            parent_artifact=tmp_path / "missing-artifact",
            baseline_score=5.0,
            baseline_evidence={},
            profile_evidence={},
        )
    assert campaign.ledger.read_bytes() == original
    assert not (tmp_path / "next").exists()


def test_historical_target_bound_contract_omits_lineage(tmp_path: Path) -> None:
    campaign = _target_campaign(tmp_path, _target())
    original = campaign.ledger.read_bytes()
    assert "lineage" not in campaign.status()["contract"]
    assert _target_campaign(tmp_path, _target()).ledger.read_bytes() == original


def test_lineage_is_frozen_and_validated() -> None:
    lineage = LoopLineage(2, "parent", "a" * 64, "winner", "b" * 64)
    with pytest.raises(FrozenInstanceError):
        lineage.loop_number = 3  # type: ignore[misc]
    for changes in (
        {"loop_number": 1},
        {"loop_number": True},
        {"parent_campaign_id": ""},
        {"parent_artifact_sha256": "bad"},
        {"baseline_source_sha256": "bad"},
    ):
        with pytest.raises(ValueError):
            replace(lineage, **changes)


@pytest.mark.parametrize("score", [0.0, -1.0, float("nan"), float("inf"), True])
def test_baseline_score_must_be_positive(tmp_path: Path, score: float) -> None:
    with pytest.raises(ValueError, match="baseline score"):
        ForgeCampaign(
            tmp_path / "forge.jsonl",
            _campaign(tmp_path).contract,
            baseline_id="baseline",
            baseline_score=score,
            baseline_evidence={},
            profile_evidence={},
        )
