# ADR-0006: Fixture Accelerator artifact

- Status: Accepted
- Date: 2026-09-25

## Decision

Stage 1 produces a directory with `manifest.json`, `benchmark.json`, and the
public Raddle wheel. The manifest schema starts at 1 and identifies one
canonical orbit case, the reference, one existing candidate, their invocation,
the declared input domain, a standalone reference baseline, the checked
benchmark receipt, reproduction commands, and SHA-256 hashes of both files.
It labels the orbit example as a fixture. The receipt retains numerical
tolerances, validation diagnostics, every timed repetition, timing scope,
hardware, and software provenance. No speed threshold is a correctness gate.

The workflow measures the reference before executing the candidate. It rejects
a mismatch before candidate timing or artifact creation. The existing
`orbit.benchmark` then measures a paired baseline and candidate after its own
validation gate; this preserves the established benchmark method and receipt
schema. Case construction and wheel building are excluded from timings.

The wheel is a whole-package distribution selected by the manifest, not a new
per-candidate package format. Artifact creation checks its packaged Python
sources against the running Raddle sources; its hash then identifies those
packaged bytes. This does not attest to dynamic monkeypatching or dependency
binary identities. Reproduction means repeating the declared
case and measurement on a recorded environment, not identical timing values.

## Scope

Only existing orbit candidates and canonical inputs can enter this workflow.
There is no external workload intake, optimizer, plugin system, hosted Run,
Deploy integration, or platform artifact consumer. The public descriptor and
receipt schemas remain unchanged, so the current platform catalog continues
to read them without migration.
