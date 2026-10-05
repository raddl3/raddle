---
name: raddle-accelerate
description: Trace and lock one approved workload, profile it, propose acceleration, and evaluate isolated candidates with Raddle Forge.
---

# Accelerate one approved workload

The coding agent or engineer produces candidates; Raddle supplies the harness.
Source and data stay in the user's environment. Use trusted project commands.

DISCOVER → TRACE EXECUTION PATH → PROPOSE TARGET → USER APPROVES TARGET
→ PROFILE → PROPOSE ACCELERATION PLAN → USER APPROVES PLAN
→ ISOLATED CANDIDATE WORK → FORGE EVALUATION → ARTIFACT

1. Read project instructions and [scoping.md](references/scoping.md). Trace from
   the user-named entrypoint; propose one target with explicit exclusions. Ask
   **"Is this the workload you want accelerated?"** and STOP until approved.
   Do this before expensive profiling, model downloads, credential use or candidates.
2. Profile only the approved path and representative case. Consult
   [opportunities.md](references/opportunities.md) and, for ML inference,
   [ml-inference.md](references/ml-inference.md). Static inspection is unmeasured.
3. Propose the evidence-based acceleration plan, validation, implementation scope,
   compute, commands and experiment budget. Stop for review until the user approves.
   Never invent numerical speedups. Existing approval must cover this exact target/plan.
4. Build after approval in an isolated Git worktree from the agreed revision.
   Preserve the trusted reference and unrelated/uncommitted work. Bind new Forge
   campaigns to the approved `AccelerationTarget`; changed scope needs a new
   target and campaign, with renewed approval.
5. Use workload-owned callbacks and [external-workload.md](references/external-workload.md).
   Forge validation gates benchmarking; retain rejected attempts and budget.
   Follow [evaluation.md](references/evaluation.md) for measurement boundaries.
6. Package only an accepted incumbent using [artifacts.md](references/artifacts.md).
   Read back the Accelerator artifact and report evidence, provenance and commands.
   Require review before adoption.

`raddle list` / `raddle inspect <id> --json` describe built-in contracts only;
they do not validate arbitrary project workloads.
