# Accelerate an existing project

Raddle comes to your repository. Source code and workload data stay in your
environment; no upload to Raddle is required. A coding agent or engineer
inspects the project and creates candidates. Initialization installs guidance,
not an autonomous optimizer or a workload discovery service.

1. **Add Raddle to your project.** Raddle is distributed from public Git, not
   PyPI. Install the pinned public tool, then initialize from your repository root:

   ```sh
   uv tool install --python 3.12 git+https://github.com/raddl3/raddle@62ce3c025c747f4793b2a3bd373c8c1afa81815b
   raddle agent init
   ```

   The tool is separate from your project environment. Codex uses `.agents/skills/raddle-accelerate/`;
   Claude Code uses `.claude/skills/raddle-accelerate/`. Choose with
   `--agent codex` or `--agent claude`; preview with `--dry-run`. Modified
   installed files are never overwritten. For library integration use
   `uv add git+https://github.com/raddl3/raddle@62ce3c025c747f4793b2a3bd373c8c1afa81815b`. Your project needs Python 3.12+; pin it with
   `uv python pin 3.12` if needed. On Linux CUDA 12, install the backend with
   `uv add "raddle[cuda12] @ git+https://github.com/raddl3/raddle@62ce3c025c747f4793b2a3bd373c8c1afa81815b"`. The optional kickoff text is also installed in `KICKOFF.md`.
2. **Inspect the workload.** Use trusted project test and profiling commands.
   Record the reference calculation, inputs, outputs, numerical method,
   representative size, CPU baseline, and measured hotspot. Use
   `raddle list` and `raddle inspect <id> --json` to compare contracts.
   These inspect public accelerators, not arbitrary project code.
3. **Review the acceleration plan.** Before candidate edits, review the proposed
   change, semantics, tolerances, cases, timing boundary (including setup and
   transfers), compute, and exact commands. Static inspection and GPU paths
   without GPU measurements must be labeled **unmeasured**. No numerical GPU
   speedup estimates. If a compatible accelerator or adapter is missing, return
   a bounded Forge candidate report and identify the integration work.
4. **Build and verify.** After plan approval, create an isolated Git worktree
   from the agreed revision, for example:
   `git worktree add -b raddle/candidate ../project-raddle-candidate HEAD`.
   This includes committed files only: agree how to carry relevant uncommitted
   changes; do not silently commit, discard them, or copy private files.
   Keep the original calculation as the reference. A coding agent or engineer
   creates the candidate in that worktree. With no Git repository, establish
   isolation with the user before editing.

Evaluate on a supported local GPU or [existing user-controlled remote GPU over
SSH](ssh-evaluation.md). With no GPU, CPU profiling and planning can continue,
but GPU paths remain unmeasured. Raddle does not emulate GPUs or provision compute.

Use the workload's existing Forge adapter. Forge builds and validates candidates
against the reference before it permits benchmarking. Compare the same workload
and state the timing boundary and environment. Built-in `raddle verify` and
`raddle benchmark` cover their own canonical cases; their receipts do not prove
correctness or speedup for your project.

Review validation, provenance, raw timings, and reproduction commands. Failed or
unmeasured candidates cannot become accepted GPU results. Use the workload's
existing artifact packaging flow for an accepted candidate and verify it with
`raddle.artifact.read_artifact`. Packaging requires the existing artifact
contract, including source/package identities and evidence; it is not a generic
CLI command for arbitrary repositories. Adoption in the original project is a
separate user review, not an automatic merge.
