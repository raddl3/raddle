# Trace and lock the target

Start with project instructions and the user-named entrypoint (for example,
"the inference path"). Read call sites, configuration, scripts and tests to trace
its actual execution path. If multiple active paths remain plausible, ask which
one the user means. A slow function is not in scope merely because it exists.
Legacy, archived, benchmark, experimental and unrelated paths stay excluded
unless reachable from the approved execution path. Record evidence of reachability;
distinguish current production/research use from merely available code.

Before expensive profiling, model downloads, repository credential use or candidate
work, propose ONE target:

- stable target/workload ID and concrete entrypoint/invocation;
- representative input/case identity (parameters and hashes, not large inputs);
- objective: warm latency, cold latency, throughput, training step time, etc.;
- timing boundary, included setup/transfers/synchronization and excluded work;
- trusted reference: revision, adapter/model artifact hashes and relevant settings;
- included and excluded components/paths, with execution-path evidence;
- compute target/constraints where relevant.

Ask exactly: **"Is this the workload you want accelerated?"** STOP until the user
approves that target. Record their approval evidence, without credentials or private
conversation content. Static inspection may establish reachability; it does not
establish a measured bottleneck. Run tests/profile only within the approved scope.

Require explicit approval before widening scope, using repository credentials,
downloading private/model artifacts, or transferring workload data elsewhere.
Target approval alone does not grant these permissions. Changed scope, objective,
boundary, reference or case requires a new target/campaign and renewed approval;
never quietly broaden the old campaign.

After approval, construct `raddle.forge.AccelerationTarget`. Strings and tuples
contain identity/evidence only, no callbacks. Use relative paths, artifact hashes
and sanitized invocations; exclude secrets, usernames, hostnames and private
absolute paths. `approval` records the user's decision; Forge cannot authenticate it.

Recommended project-local state: `.raddle/campaigns/<campaign-id>/forge.jsonl`,
`candidates/`, `artifacts/`. The first ledger row contains the complete target and
canonical `target_sha256`; it is the authoritative inspectable target, so a separate
`target.json` is unnecessary. Bind it via `ForgeContract(..., target=target)`.
Reopen with identical contract and baseline/profile evidence. Keep large inputs
outside campaign state; store only their identities. Add `.raddle/` to the project's
Git ignore after checking its conventions, or deliberately preserve reviewed,
sanitized evidence. Do not rewrite historical ledgers to attach targets.
