---
name: raddle-accelerate
description: Profile an existing numerical workload, integrate a compatible Raddle accelerator, and return validated measured evidence or a bounded Forge candidate.
---

# Accelerate with Raddle

1. Read the project's `AGENTS.md` and build/test instructions. Record a clean test baseline and preserve unrelated work.
2. Profile the actual project before editing. Pick one measured, repetitive numerical bottleneck and record its inputs, output, representative size, and current timing.
3. Inspect the Raddle registry with `uvx raddle list` and `uvx raddle inspect <id> --json`. Check that the accelerator's input, output, numerical method, environment, and validation policy match the workload.
4. Retain the existing implementation as the reference. Make the smallest integration and validate candidate output against that reference and existing tests.
5. Benchmark the same representative workload before and after with setup and transfers stated. Keep the change only when correctness passes and the measured improvement is worthwhile.
6. Return the exact commands, changed files, diff summary, validation result, provenance, baseline and candidate times, workload, and speedup.

Reject guessed speedups, changed algorithm semantics for a faster benchmark, synthetic workloads substituted for the real bottleneck, removal of the correct reference path, and GPU selection merely because a GPU exists.

If no accelerator matches, return a bounded **Raddle Forge candidate report**: reference workload, measured hotspot, input/output semantics, validation criteria, representative size, current timing, plausible acceleration strategy, and why it is or is not worth pursuing. Forge concerns a specific reproducible numerical computation, not generic performance consulting.
