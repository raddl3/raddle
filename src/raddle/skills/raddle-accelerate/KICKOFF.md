Use the Raddle acceleration skill in this repository.

Profile the existing project using trusted workload commands and preserve its reference calculation and correctness tests. Keep source and data in my environment; no upload to Raddle is required.

First return an acceleration plan for my review: the measured hotspot (or label static inspection as unmeasured), reference semantics, proposed candidate, validation criteria, representative workload, timing boundary, suitable compute, and exact commands. Stop before candidate edits until I approve the plan.

After approval, have the coding agent or engineer build the candidate in an isolated Git worktree. Evaluate on a local GPU or my existing SSH-accessible GPU machine. Without GPU measurements, label GPU paths unmeasured and do not claim a numerical GPU speedup.

Use the workload's Forge validation gate before benchmarking. If an adapter is missing, follow the installed external-workload reference and public executable example to implement the workload-owned callbacks within the approved plan. Return validated evidence, provenance, changed files, and reproduction commands; package and read back an accepted Accelerator artifact using create_external_artifact and read_artifact before proposing adoption.
