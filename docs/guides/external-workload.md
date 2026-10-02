# Integrate an external workload

Start with the runnable [external-workload example](../../examples/external-workload/README.md).
It demonstrates the complete public path without a backend, optimizer, registry,
or hosted service. The workload owns its code and callbacks.

## Establish the contract before candidate work

Preserve the reference callable, representative inputs and all externally relevant
outputs. Record the reference source revision, adapter/input hashes, case parameters,
precision, and validation policy. Use JSON-serializable identities in `ForgeContract`;
do not mutate their nested dictionaries after construction. The ledger checks the
canonical serialized contract on reopening; changed identities require a new campaign.

Measure a standalone reference baseline and a real profile first. Record raw
samples, warm-up, clock, timing boundary, hardware/software, setup, transfers and
synchronization. A static guess is not a profile. Pass this evidence to
`ForgeCampaign(ledger, contract, baseline_id=..., baseline_score=...,
baseline_evidence=..., profile_evidence=...)`. Scores must use a consistent unit;
for elapsed time, lower is better.

## Supply the existing callback contract

`ForgeCampaign.evaluate` takes keyword-only candidate source, source store,
experiment ID, parent experiment ID, metadata, and these callbacks:

| Callback | Return | Workload responsibility |
| --- | --- | --- |
| `build(snapshot: Path)` | `(candidate: object, evidence: object)` | Compile/load the supplied immutable source snapshot, retain build evidence. |
| `validate(candidate: object)` | `Mapping[str, object]` | Compare reference and candidate using the fixed policy. Only `status="matched"` permits timing. Include diagnostics and all relevant outputs. |
| `benchmark(candidate: object)` | `BenchmarkResult(evidence, score, eligible=True)` | Measure the same case and boundary; supply raw evidence, finite positive score, and any eligibility/rejection policy. |

Forge snapshots and hashes candidate source before build. Failed build or validation
records a rejection; benchmark is never called after a validation failure. Eligibility
and improvement over the incumbent both matter. A valid but slower candidate is
not accepted. `status()` reports experiments, budget and incumbent;
`incumbent_source()` verifies the accepted snapshot's hash before returning it.
A baseline incumbent has no candidate source to package.

Reopen with the identical contract, baseline and profile evidence to inspect or
resume. An interrupted started experiment can resume with its original ID and
identities; a completed experiment cannot run again under the same ID. Keep the
ledger and source store together. The example deliberately starts a fresh directory
rather than implementing a separate campaign manager.

## Package only the accepted incumbent

Build the workload wheel from the accepted snapshot, not the current working file.
Check that its candidate member bytes hash to the incumbent identity. Build the
Raddle wheel from the same source as the running Raddle package; packaging checks
its sources. Retain the workload's locked dependency environment.

Call `create_external_artifact` with:

- `AcceleratorDescriptor`, `ExternalCaseDescriptor`, implementation IDs, declared
  input/output contracts and `ValidationPolicy`;
- reference/candidate callables and a validator returning `ValidationReceipt`;
- canonical `inputs_json` with `case == asdict(case)`;
- reference URL/full `git:<40-character revision>`, invocations, validation method,
  profile (including a nonempty `top` list of measured functions) and dependency versions;
- Raddle/workload wheels, package names/versions, exact candidate source member,
  lockfile, output path, repetition/warm-up and reproduction commands.

The API remeasures the baseline, validates again before candidate timings, then
writes the manifest, benchmark receipt, inputs, lockfile and wheels. This is a
separate measured run from Forge selection; retain both without substituting one
for the other. Artifact creation does not decide campaign acceptance for you.

Finally call `read_artifact(output)`. It verifies content digests and contract
consistency. Compare its candidate source identity with the Forge incumbent and
review the evidence before adoption. Readback checks integrity; it does not rerun
validation or certify arbitrary wheel behavior. The workload must ensure the
executed candidate is the packaged candidate, as the example does.

For GPU workloads, synchronize at timing boundaries and state end-to-end versus
device-only scope. Use [manual SSH](ssh-evaluation.md) for existing remote compute;
there is no Raddle SSH executor. Without suitable compute, keep candidates unmeasured.
