# Compute and evidence boundaries

Measure only the approved target, objective and timing boundary. Target lock and
plan approval precede candidate work; changing scope requires a new campaign.

Local: run workload callbacks on suitable CPU/GPU hardware. Capture hardware,
software, raw samples, warm-up and scope. Include setup/transfers for end-to-end
claims; synchronize GPU execution before/after measured calls.

Remote, only when explicitly approved as part of the target: use the user's
existing SSH access and workload commands. Follow the
[manual SSH workflow](https://github.com/raddl3/raddle/blob/main/docs/guides/ssh-evaluation.md).
Stage only reviewed code and authorized inputs; retrieve the ledger, immutable
sources, receipts and artifact. Raddle has no SSH executor or compute provisioning.

No GPU: CPU profiling, adapter integration and CPU measurements can proceed.
Keep GPU candidates unmeasured until executed on suitable compute. Never infer a
GPU speedup from CPU timings or a static profile.

Built-in `raddle verify` / `benchmark` evaluate only declared canonical cases.
They do not validate arbitrary project workloads. Keep reference/case/policy fixed,
compare all relevant outputs, reject incorrect candidates before benchmarking,
and distinguish recorded campaign timings from separate artifact measurements.
