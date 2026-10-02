---
name: raddle-accelerate
description: Inspect an existing numerical workload, plan an isolated candidate, and integrate Raddle Forge validation, measurement, and accepted artifacts.
---

# Accelerate an existing project

Codex, Claude, or an engineer produces candidates; Raddle supplies the harness.
Source and data stay in the user's environment. Use trusted project commands.

1. **Inspect.** Read project instructions, run the existing test baseline, and
   profile a representative case. Preserve the reference and relevant outputs.
   `raddle list` / `raddle inspect <id> --json` describe built-in contracts only.
2. **Plan, then stop for review.** State the measured hotspot, reference semantics,
   candidate, validation policy/cases, timing boundary, compute and commands.
   Honor approval already given in the session. Label unavailable measurements
   unmeasured; never estimate GPU speedups.
3. **Build in isolation.** After approval, use an isolated Git worktree from the
   agreed revision; preserve unrelated/uncommitted work. Keep the reference.
4. **Forge.** Use existing workload callbacks. If missing, implement the public
   callback contract using [external-workload.md](references/external-workload.md),
   rather than stopping at a missing-adapter report. Forge gates benchmarking
   on validation; failed candidates remain rejected in the ledger.
5. **Artifact.** For an accepted incumbent, follow
   [artifacts.md](references/artifacts.md): package accepted bytes, validate,
   measure and check readback before proposing adoption.

Read [evaluation.md](references/evaluation.md) when choosing local versus manual
SSH evaluation or working without GPU access. Return commands, changes, validation,
raw evidence, source/environment identities and measured results. Adoption/merge
requires user review. Do not replace semantics or substitute a synthetic case for
the project's bottleneck.
