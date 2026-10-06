"""Small, workload-neutral campaign state and candidate evaluation gate."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class AccelerationTarget:
    """Approved workload identity/evidence, never execution instructions."""

    target_id: str
    invocation: str
    representative_case: str
    objective: str
    timing_boundary: str
    trusted_reference: str
    included_paths: tuple[str, ...]
    excluded_paths: tuple[str, ...]
    approval: str
    compute_constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if name in {"included_paths", "excluded_paths", "compute_constraints"}:
                if not isinstance(value, tuple) or any(
                    not isinstance(item, str) or not item.strip() for item in value
                ):
                    raise ValueError(f"{name} must be a tuple of nonempty strings")
            elif not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a nonempty string")
        if not self.included_paths:
            raise ValueError("included_paths must identify the execution path")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(_json(asdict(self)).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LoopLineage:
    """Link a fresh performance baseline to its adopted parent winner."""

    loop_number: int
    parent_campaign_id: str
    parent_artifact_sha256: str
    baseline_id: str
    baseline_source_sha256: str

    def __post_init__(self) -> None:
        if type(self.loop_number) is not int or self.loop_number < 2:
            raise ValueError("later loop numbers must be integers >= 2")
        if not self.parent_campaign_id or not self.baseline_id:
            raise ValueError("parent campaign and baseline identities are required")
        for digest in (self.parent_artifact_sha256, self.baseline_source_sha256):
            if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise ValueError("lineage hashes must be SHA-256 hex digests")


@dataclass(frozen=True)
class ForgeContract:
    """Immutable identity and acceptance contract for one campaign case."""

    campaign_id: str
    reference_identity: Mapping[str, object]
    case_identity: Mapping[str, object]
    validation_policy: Mapping[str, object]
    budget: int
    target: AccelerationTarget | None = None
    lineage: LoopLineage | None = None

    def __post_init__(self) -> None:
        if not self.campaign_id or type(self.budget) is not int or self.budget <= 0:
            raise ValueError("campaign ID and positive experiment budget are required")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        if self.target is None:
            del result["target"]  # Preserve the historical serialized contract.
        else:
            result["target_sha256"] = self.target.sha256
        if self.lineage is None:
            del result["lineage"]  # No migration for v0.4.x contracts.
        return result


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
        if (
            isinstance(baseline_score, bool)
            or not math.isfinite(baseline_score)
            or baseline_score <= 0
        ):
            raise ValueError("baseline score must be finite and positive")
        if contract.lineage is not None and baseline_id != contract.lineage.baseline_id:
            raise ValueError("baseline identity differs from loop lineage")
        self.ledger = ledger
        self.contract = contract
        self._contract_identity = _json(contract.to_dict())
        self.event = event
        self.legacy_record_identity = legacy_record_identity
        self.legacy_score = legacy_score
        self._append(
            "forge-campaign",
            {
                "campaign_id": contract.campaign_id,
                "contract": json.loads(self._contract_identity),
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
        self._check_contract()
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

    def _check_contract(self) -> None:
        if _json(self.contract.to_dict()) != self._contract_identity:
            raise ValueError("Forge campaign contract or target changed")

    def status(self) -> dict[str, Any]:
        self._check_contract()
        rows = self._rows()
        campaign = next(
            row["record"]
            for row in rows
            if row["event"] == "forge-campaign"
            and row["record"].get("campaign_id") == self.contract.campaign_id
        )
        if _json(campaign["contract"]) != self._contract_identity:
            raise ValueError("Forge campaign contract or target changed")

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
            "baseline_id": campaign["baseline_id"],
            "baseline_score": campaign["baseline_score"],
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

    def record_artifact(self, artifact: Path) -> str:
        """Read back an external artifact and bind its manifest to this winner."""
        from raddle.artifact import read_artifact
        from raddle.contracts import ExternalAcceleratorArtifact

        manifest = read_artifact(artifact)
        incumbent = self.status()["incumbent"]
        self.incumbent_source()
        if not isinstance(manifest, ExternalAcceleratorArtifact) or (
            manifest.candidate_source_revision
            != "sha256:" + incumbent["candidate_source_hash"]
        ):
            raise ValueError("artifact does not contain the accepted incumbent")
        digest = hashlib.sha256((artifact / "manifest.json").read_bytes()).hexdigest()
        record = {
            "campaign_id": self.contract.campaign_id,
            "experiment_id": incumbent["experiment_id"],
            "candidate_source_hash": incumbent["candidate_source_hash"],
            "artifact_manifest_sha256": digest,
        }
        if not any(
            row["event"] == "forge-artifact" and row["record"] == record
            for row in self._rows()
        ):
            self._append("forge-artifact", record)
        return digest

    def next_loop(
        self,
        ledger: Path,
        *,
        campaign_id: str,
        budget: int,
        target: AccelerationTarget,
        approved: bool,
        adopted_source: Path,
        parent_artifact: Path,
        baseline_score: float,
        baseline_evidence: object,
        profile_evidence: object,
    ) -> ForgeCampaign:
        """After opt-in and fresh plan approval, open an independent campaign.

        Callers measure/profile the verified adopted workload anew, then obtain
        approval for the new plan and budget before calling this method. Execution
        and correctness validation remain workload-owned; reference identity is
        inherited unchanged. This method never profiles or runs candidates.
        """
        if approved is not True:
            raise ValueError("explicit user approval required for another loop")
        if self.contract.target is None or target != self.contract.target:
            raise ValueError(
                "changed or missing target requires renewed target approval"
            )
        self.incumbent_source()
        incumbent = self.status()["incumbent"]
        source_hash = hashlib.sha256(adopted_source.read_bytes()).hexdigest()
        if source_hash != incumbent["candidate_source_hash"]:
            raise ValueError("adopted source differs from accepted incumbent")
        # Readback verifies all artifact members, without writing the parent ledger.
        from raddle.artifact import read_artifact
        from raddle.contracts import ExternalAcceleratorArtifact

        manifest = read_artifact(parent_artifact)
        digest = hashlib.sha256(
            (parent_artifact / "manifest.json").read_bytes()
        ).hexdigest()
        if not isinstance(manifest, ExternalAcceleratorArtifact) or (
            manifest.candidate_source_revision != "sha256:" + source_hash
        ):
            raise ValueError("parent artifact differs from adopted incumbent")
        if not any(
            row["event"] == "forge-artifact"
            and row["record"].get("campaign_id") == self.contract.campaign_id
            and row["record"].get("experiment_id") == incumbent["experiment_id"]
            and row["record"].get("artifact_manifest_sha256") == digest
            for row in self._rows()
        ):
            raise ValueError("parent artifact must be recorded before another loop")
        if (
            campaign_id == self.contract.campaign_id
            or ledger.exists()
            or ledger.parent.resolve().is_relative_to(self.ledger.parent.resolve())
            or self.ledger.parent.resolve().is_relative_to(ledger.parent.resolve())
        ):
            raise ValueError("another loop requires a new campaign ID and directory")
        lineage = LoopLineage(
            2
            if self.contract.lineage is None
            else self.contract.lineage.loop_number + 1,
            self.contract.campaign_id,
            digest,
            incumbent["experiment_id"],
            source_hash,
        )
        return ForgeCampaign(
            ledger,
            replace(
                self.contract, campaign_id=campaign_id, budget=budget, lineage=lineage
            ),
            baseline_id=incumbent["experiment_id"],
            baseline_score=baseline_score,
            baseline_evidence=baseline_evidence,
            profile_evidence=profile_evidence,
        )

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
