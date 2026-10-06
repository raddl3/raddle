# ADR-0009: Explicit acceleration loops

Each adopted winner may seed another loop only after explicit user opt-in.
Fresh measurement and profiling precede a new plan approval and experiment budget.
An accepted candidate alone does not establish an adopted performance baseline.
No scheduler, autonomous search policy or campaign manager is introduced.

`AccelerationTarget` remains unchanged: the approved workload and original trusted
reference are stable. `ForgeContract.reference_identity`, case and validation policy
remain anchored to that reference. The adopted winner is a separate performance
baseline in a new campaign, with fresh evidence and score. Artifact validation and
reference timings continue to use the original reference, not the incumbent.

An optional frozen `LoopLineage` records loop number, parent campaign ID, parent
artifact manifest SHA-256, performance baseline incumbent ID and source SHA-256.
Absent lineage means loop 1 (or historical campaign); serialization omits it.
The existing campaign row records target/hash, budget, baseline and profile.
Experiment records identify the accepted incumbent. A `forge-artifact` record binds
its verified external artifact manifest hash to the campaign and experiment.
Artifacts retain their existing schema. Content hashes identify artifacts without
private absolute paths; the enclosing campaign directory supplies their location.

`record_artifact` checks artifact readback against the accepted source snapshot.
`next_loop` checks opt-in, unchanged target, adopted source and recorded artifact,
then creates an independent contract/ledger in a new directory with a fresh budget.
It never writes the parent ledger or starts profiling. Changed workloads require a
new target approval, not a lineage link. Historical targetless and target-bound
campaigns remain readable without rewriting or migration.

The workload/agent owns approval evidence, apply/verify, fresh measurements,
profiling and callback correctness. Boolean approval and matching source hashes
are guards, not authenticated consent or proof of execution semantics. The skill
stops after offering another loop and again for the new plan approval. No accepted
or verified adopted incumbent means trying a different plan, not another loop.

The focused two-loop integration fixture scripts only selection scores to avoid
CI timing thresholds; it executes callbacks and creates/readbacks real artifacts.
The normal external-workload example retains measured selection and reproduction.
