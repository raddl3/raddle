# Raddle documentation

- [Accelerate an existing project](guides/accelerate.md): install, inspect, plan,
  isolate a candidate, and choose local or manual SSH evaluation.
- [External workload integration](guides/external-workload.md): Forge callbacks,
  identities, acceptance, artifact packaging, and checked readback.
- [Executable example](../examples/external-workload/README.md): a complete CPU
  integration with no hosted services or performance claim.
- [Accelerator contracts](concepts/accelerator.md): inputs, outputs, validation,
  provenance, and artifact formats.
- [Manual SSH evaluation](guides/ssh-evaluation.md): current manual workflow and
  deferred executor design.
- [Public Python API](../src/raddle/): `forge.py`, `artifact.py`, `contracts.py`,
  and `evidence.py` are the implementation and contract source of truth.
- [Architecture decisions](architecture/) and [development history](architecture/product-history.md).

Run `task ci` for locked tests, strict mypy typing, lint, evidence checks,
security scans, and package builds. Run `task example` for the external integration.
