# When the workload has no adapter

Use the [complete example](https://github.com/raddl3/raddle/tree/main/examples/external-workload)
and [callback guide](https://github.com/raddl3/raddle/blob/main/docs/guides/external-workload.md).

Preserve reference source/revision and representative input/case/policy identities.
Measure baseline and profile before constructing `ForgeContract` / `ForgeCampaign`.
Use the identical contract and baseline/profile evidence when reopening a campaign.

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
