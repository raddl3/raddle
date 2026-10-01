from pathlib import Path

import pytest

from raddle.forge import BenchmarkResult, ForgeCampaign, ForgeContract


def _campaign(tmp_path: Path, budget: int = 2) -> ForgeCampaign:
    return ForgeCampaign(
        tmp_path / "forge.jsonl",
        ForgeContract(
            "case.one", {"revision": "abc"}, {"size": 4}, {"atol": 0.0}, budget
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
    campaign = _campaign(tmp_path, budget=1)
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

    resumed = _campaign(tmp_path, budget=1)
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
