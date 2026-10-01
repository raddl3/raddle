"""Small, workload-neutral campaign state and candidate evaluation gate."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class ForgeContract:
    """Immutable identity and acceptance contract for one campaign case."""

    campaign_id: str
    reference_identity: Mapping[str, object]
    case_identity: Mapping[str, object]
    validation_policy: Mapping[str, object]
    budget: int

    def __post_init__(self) -> None:
        if not self.campaign_id or type(self.budget) is not int or self.budget <= 0:
            raise ValueError("campaign ID and positive experiment budget are required")


@dataclass(frozen=True)
class BenchmarkResult:
    """Opaque benchmark evidence plus a lower-is-better incumbent score."""

    evidence: object
    score: float
    eligible: bool = True
    rejection_reason: str | None = None


@dataclass(frozen=True)
class ForgeEvaluation:
    candidate: object | None
    record: dict[str, Any]


class ForgeCampaign:
    """Append-only campaign ledger; workload callbacks own execution details."""

    def __init__(
        self,
        ledger: Path,
        contract: ForgeContract,
        *,
        baseline_id: str,
        baseline_score: float,
        baseline_evidence: object,
        profile_evidence: object,
        event: str = "forge-experiment",
        legacy_record_identity: tuple[str, str] | None = None,
        legacy_score: Callable[[Mapping[str, Any]], float | None] | None = None,
    ) -> None:
        self.ledger = ledger
        self.contract = contract
        self.event = event
        self.legacy_record_identity = legacy_record_identity
        self.legacy_score = legacy_score
        self._append(
            "forge-campaign",
            {
                "campaign_id": contract.campaign_id,
                "contract": json.loads(_json(contract.__dict__)),
                "baseline_id": baseline_id,
                "baseline_score": baseline_score,
                "baseline": baseline_evidence,
                "profile": profile_evidence,
            },
        )

    def _rows(self) -> list[dict[str, Any]]:
        if not self.ledger.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line_number, line in enumerate(
            self.ledger.read_text(encoding="utf-8").splitlines(), 1
        ):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"invalid Forge JSONL at line {line_number}"
                ) from error
            if not isinstance(row, dict) or not isinstance(row.get("record"), dict):
                raise ValueError(f"invalid Forge record at line {line_number}")
            rows.append(row)
        return rows

    def _append(self, event: str, record: dict[str, Any]) -> None:
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        rows = self._rows()
        campaigns = [
            row["record"]
            for row in rows
            if row["event"] == "forge-campaign"
            and row["record"].get("campaign_id") == self.contract.campaign_id
        ]
        if event == "forge-campaign":
            encoded = _json(record)
            if campaigns:
                if _json(campaigns[0]) != encoded:
                    raise ValueError("Forge campaign contract or baseline changed")
                return
        elif not campaigns:
            raise ValueError("Forge campaign has not been initialized")
        payload = _json({"event": event, "record": record}) + "\n"
        with self.ledger.open("a", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

    def status(self) -> dict[str, Any]:
        rows = self._rows()
        campaign = next(
            row["record"]
            for row in rows
            if row["event"] == "forge-campaign"
            and row["record"].get("campaign_id") == self.contract.campaign_id
        )

        def matches_campaign(record: Mapping[str, Any]) -> bool:
            return record.get("campaign_id") == self.contract.campaign_id or (
                self.legacy_record_identity is not None
                and record.get(self.legacy_record_identity[0])
                == self.legacy_record_identity[1]
            )

        attempts = [
            row["record"]
            for row in rows
            if row["event"] == self.event
            and matches_campaign(row["record"])
            and row["record"].get("status") in ("started", "experiment")
        ]
        experiments = [row for row in attempts if row.get("status") == "experiment"]
        incumbent_id = campaign["baseline_id"]
        incumbent_score = float(campaign["baseline_score"])
        incumbent_hash = None
        incumbent_snapshot = None
        for row in experiments:
            score = row.get("score")
            if score is None and self.legacy_score is not None:
                score = self.legacy_score(row)
            if (
                row.get("accepted")
                and score is not None
                and float(score) < incumbent_score
            ):
                incumbent_id = row["experiment_id"]
                incumbent_score = float(score)
                incumbent_hash = row["candidate_source_hash"]
                incumbent_snapshot = row["candidate_snapshot"]
        return {
            "campaign_id": self.contract.campaign_id,
            "contract": campaign["contract"],
            "baseline": campaign["baseline"],
            "profile": campaign["profile"],
            "experiments": experiments,
            "attempts_used": len({row["experiment_id"] for row in attempts}),
            "remaining_budget": self.contract.budget
            - len({row["experiment_id"] for row in attempts}),
            "incumbent": {
                "experiment_id": incumbent_id,
                "score": incumbent_score,
                "candidate_source_hash": incumbent_hash,
                "candidate_snapshot": incumbent_snapshot,
            },
        }

    def incumbent_source(self) -> Path:
        """Return the verified winning source for existing artifact packaging."""
        incumbent = self.status()["incumbent"]
        relative = incumbent["candidate_snapshot"]
        if not isinstance(relative, str):
            raise ValueError("the reference baseline is still the incumbent")
        source = self.ledger.parent / relative
        if (
            hashlib.sha256(source.read_bytes()).hexdigest()
            != incumbent["candidate_source_hash"]
        ):
            raise ValueError("incumbent candidate snapshot hash mismatch")
        return source

    def evaluate(
        self,
        *,
        candidate_source: Path,
        source_store: Path,
        experiment_id: str,
        parent_experiment: str,
        metadata: Mapping[str, object],
        build: Callable[[Path], tuple[object, object]],
        validate: Callable[[object], Mapping[str, object]],
        benchmark: Callable[[object], BenchmarkResult],
    ) -> ForgeEvaluation:
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", experiment_id) is None:
            raise ValueError("invalid Forge experiment ID")
        records = [
            row["record"]
            for row in self._rows()
            if row["event"] == self.event
            and (
                row["record"].get("campaign_id") == self.contract.campaign_id
                or (
                    self.legacy_record_identity is not None
                    and row["record"].get(self.legacy_record_identity[0])
                    == self.legacy_record_identity[1]
                )
            )
            and row["record"].get("experiment_id") == experiment_id
        ]
        starts = [row for row in records if row.get("status") == "started"]
        terminals = [row for row in records if row.get("status") == "experiment"]
        if terminals:
            raise ValueError("Forge experiment is already complete")
        if records and not starts:
            raise ValueError("Forge experiment ID has already been used")
        source = candidate_source.resolve(strict=True)
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        state = self.status()
        if not starts and state["remaining_budget"] <= 0:
            raise ValueError("Forge experiment budget is exhausted")
        if starts:
            original = starts[0]
            original_metadata = {
                key: value
                for key, value in original.items()
                if key
                not in {
                    "campaign_id",
                    "experiment_id",
                    "parent_experiment",
                    "candidate_source_revision",
                    "candidate_source_hash",
                    "candidate_snapshot",
                    "status",
                    "resumed",
                }
            }
            if (
                original.get("candidate_source_hash") != source_hash
                or original.get("parent_experiment") != parent_experiment
                or original_metadata != dict(metadata)
            ):
                raise ValueError("resume identity differs; use a new experiment ID")
            snapshot_relative = original.get("candidate_snapshot")
            if not isinstance(snapshot_relative, str):
                raise ValueError("original candidate snapshot is missing")
            snapshot = (self.ledger.parent / snapshot_relative).resolve(strict=True)
            if (
                hashlib.sha256(snapshot.read_bytes()).hexdigest() != source_hash
                or original.get("campaign_id") != self.contract.campaign_id
            ):
                raise ValueError("resume candidate or campaign identity differs")
            snapshot_relative_path = Path(snapshot_relative)
            self._append(
                self.event,
                {**original, "status": "started", "resumed": True},
            )
        else:
            snapshot = (source_store / experiment_id / source.name).resolve()
            try:
                snapshot_relative_path = snapshot.relative_to(
                    self.ledger.parent.resolve()
                )
            except ValueError as error:
                raise ValueError(
                    "candidate snapshots must stay inside the campaign output"
                ) from error
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, snapshot)
            if hashlib.sha256(snapshot.read_bytes()).hexdigest() != source_hash:
                raise OSError("Forge candidate snapshot hash mismatch")
        snapshot_relative = snapshot_relative_path.as_posix()
        common = {
            **metadata,
            "campaign_id": self.contract.campaign_id,
            "experiment_id": experiment_id,
            "parent_experiment": parent_experiment,
            "candidate_source_revision": f"sha256:{source_hash}",
            "candidate_source_hash": source_hash,
            "candidate_snapshot": snapshot_relative,
        }
        if not starts:
            self._append(self.event, {**common, "status": "started"})
        record: dict[str, Any] = {**common, "status": "experiment"}
        candidate: object | None = None
        try:
            candidate, build_evidence = build(snapshot)
            record["build"] = build_evidence
            if (
                isinstance(build_evidence, Mapping)
                and "compile_jit_ns" in build_evidence
            ):
                record["compile_jit_ns"] = build_evidence["compile_jit_ns"]
        except Exception as error:
            record.update(
                build={"status": "failed", "error": repr(error)},
                validation=None,
                benchmark=None,
                accepted=False,
                rejection_reason="candidate build failed",
            )
            self._append(self.event, record)
            return ForgeEvaluation(None, record)
        try:
            validation = dict(validate(candidate))
        except Exception as error:
            validation = {"status": "error", "error": repr(error)}
        record["validation"] = validation
        if validation.get("status") != "matched":
            record.update(
                benchmark=None,
                accepted=False,
                rejection_reason="candidate failed validation",
            )
            self._append(self.event, record)
            return ForgeEvaluation(candidate, record)
        try:
            result = benchmark(candidate)
        except Exception as error:
            record.update(
                benchmark=None,
                accepted=False,
                rejection_reason=f"candidate benchmark failed: {error!r}",
            )
            self._append(self.event, record)
            return ForgeEvaluation(candidate, record)
        if (
            isinstance(result.score, bool)
            or not isinstance(result.score, (int, float))
            or not math.isfinite(result.score)
        ):
            record.update(
                benchmark=result.evidence,
                accepted=False,
                rejection_reason="benchmark score must be a finite number",
            )
            self._append(self.event, record)
            return ForgeEvaluation(candidate, record)
        incumbent = self.status()["incumbent"]
        accepted = result.eligible and result.score < float(incumbent["score"])
        record.update(
            benchmark=result.evidence,
            score=result.score,
            accepted=accepted,
            rejection_reason=(
                None
                if accepted
                else result.rejection_reason or "candidate did not beat incumbent"
            ),
        )
        self._append(self.event, record)
        return ForgeEvaluation(candidate, record)
