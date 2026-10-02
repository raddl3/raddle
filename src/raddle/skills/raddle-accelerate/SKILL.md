---
name: raddle-accelerate
description: Inspect a trusted workload in an existing project, propose an acceleration plan for review, and evaluate isolated candidates with validated evidence.
---

# Accelerate your existing project

Source code and workload data stay in the user's environment. No upload to Raddle is required. Use only trusted project commands and user-controlled compute.

1. **Inspect the workload.** Read the project's `AGENTS.md` and build/test instructions. Preserve unrelated work and record the existing test baseline. Profile a representative workload before editing: record inputs, outputs, numerical method, size, current timing, and one measured repetitive hotspot. If execution is unavailable, distinguish static inspection from a measured profile.
2. **Propose a plan, then stop for review.** Inspect `raddle list` and `raddle inspect <id> --json` for compatible contracts. State the reference, proposed change, input/output semantics, validation criteria and tolerances, representative cases, timing boundary including setup/transfers, compute requirements, and reproduction commands. Ask the user to approve the plan before creating or editing candidates. A likely GPU path without GPU measurements is **unmeasured**; never estimate a numerical GPU speedup.
3. **Build in isolation after approval.** Create a separate Git worktree from the agreed revision. If relevant changes are uncommitted, agree how to include them rather than dropping them or silently committing. A coding agent or engineer creates the smallest candidate there, retaining the existing calculation as the reference. If the project has no Git repository, ask how to establish isolation before candidate edits.
4. **Evaluate on suitable compute.** Use a local GPU or an existing user-controlled GPU machine with standard user-managed SSH authentication. Only stage the reviewed candidate and required inputs; do not transfer secrets, unrelated files, or workload data without authorization. With no GPU, CPU inspection/profiling and planning can continue, but GPU candidates remain unmeasured. Raddle does not provision compute.
5. **Validate before benchmarking.** Use the workload's existing Forge adapter when available: Forge gates each candidate on correctness against the reference before benchmarking the same representative workload. Do not bypass that gate. Built-in `raddle verify` / `benchmark` commands cover only their declared canonical cases, not arbitrary project validation. If no compatible accelerator or workload adapter exists, return a bounded Forge candidate report and the missing integration work rather than inventing evidence.
6. **Review the result.** Return exact commands, changed files, validation outcome, source and environment provenance, baseline and candidate times, workload, and measured speedup only when available. Keep failed or unmeasured candidates out of accepted results. Package an accepted Accelerator artifact through the workload's existing artifact flow and verify readback before proposing adoption in the original project. Do not replace the reference or merge without user review.

Reject guessed speedups, changed algorithm semantics for a faster benchmark, synthetic workloads substituted for the real bottleneck, removal of the correct reference path, and GPU selection merely because a GPU exists.
