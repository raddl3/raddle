# When the workload has no adapter

Use the [complete example](https://github.com/raddl3/raddle/tree/main/examples/external-workload)
and [callback guide](https://github.com/raddl3/raddle/blob/main/docs/guides/external-workload.md).

First lock the target using [scoping.md](scoping.md) and record user approval.
Preserve reference source/revision and representative input/case/policy identities.
Measure baseline and profile before constructing `ForgeContract` / `ForgeCampaign`.
Use the identical contract and baseline/profile evidence when reopening a campaign.
Pass `target=approved_target` to `ForgeContract`; the ledger records its SHA-256.
Use `.raddle/campaigns/<campaign-id>/forge.jsonl` with `candidates/` and `artifacts/`
unless the project already has a suitable convention. Keep identities, not inputs
or secrets, in the ledger. Historical targetless ledgers need no migration.

Supply `ForgeCampaign.evaluate` with workload-owned callbacks:
- `build(snapshot: Path) -> (candidate, build_evidence)`: load/compile the snapshot.
- `validate(candidate) -> Mapping`: compare all relevant outputs; return
  `status="matched"` only under the fixed policy.
- `benchmark(candidate) -> BenchmarkResult`: raw evidence and finite positive
  same-boundary score; lower wins. Synchronize asynchronous GPU work.

Forge owns source snapshots/hashes, validation gating, ledger, budget and incumbent.
The workload owns execution and correctness. `status()` distinguishes accepted
from merely valid candidates. `incumbent_source()` verifies the winning bytes;
no accepted candidate means no candidate artifact. Do not add an adapter framework.

## Another user-approved loop

After adoption review, apply and verify the winner, then offer another loop and
stop. Declining ends with the final result and evidence location. Approval permits
fresh measurement and profiling of the adopted incumbent, followed by a new plan;
stop again for approval of that plan and its fresh experiment budget.

Record the verified accepted external artifact with `campaign.record_artifact(path)`
before completing the parent campaign. Then leave that campaign unchanged.
After fresh plan approval call `campaign.next_loop(new_ledger, campaign_id=...,
budget=..., target=approved_target, approved=True, adopted_source=...,
parent_artifact=..., baseline_score=..., baseline_evidence=..., profile_evidence=...)`.
Use a new `.raddle/campaigns/<campaign-id>/` directory; no workload inputs are copied.
The helper checks the adopted source and recorded artifact hashes, retains target,
reference/case/policy, and records immutable `LoopLineage` in the new contract.
The lineage contains loop number, parent campaign, parent manifest hash, baseline
incumbent ID and source hash. The new campaign record supplies fresh baseline score
and profile; accepted experiment records and `forge-artifact` records identify its
winner and resulting artifact. Loop 1 has no lineage. Old ledgers need no migration.

Correctness callbacks and artifact creation must still use the original trusted
reference. Artifact reference timing remains reference timing; the next-loop Forge
baseline measures the adopted incumbent separately. Forge cannot authenticate user
approval or prove arbitrary workload callback semantics. The caller records actual
approval, verifies adoption, and supplies fresh measured evidence, never cached data.
Changed targets need renewed target approval and a separate campaign; `next_loop`
rejects them. A campaign with no accepted winner cannot seed another loop.

See `tests/test_external_workload.py` for the focused two-loop fixture. Its scripted
selection scores test state transitions only, not performance; artifact creation
and reproduction still perform real validation and timing.
