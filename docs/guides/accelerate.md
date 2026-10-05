# Accelerate an existing project

Raddle comes to your repository. Source code and workload data stay in your
environment; no upload to Raddle is required. A coding agent or engineer
inspects the project and creates candidates. Initialization installs guidance,
not an autonomous optimizer or a workload discovery service.

1. **Add Raddle to your project.** Raddle is distributed from public Git, not
   PyPI. Install the pinned public tool, then initialize from your repository root:

   ```sh
   uv tool install --python 3.12 git+https://github.com/raddl3/raddle@v0.4.1
   raddle agent init
   ```

   The tool is separate from your project environment. Codex uses `.agents/skills/raddle-accelerate/`;
   Claude Code uses `.claude/skills/raddle-accelerate/`. Choose with
   `--agent codex` or `--agent claude`; preview with `--dry-run`. Modified
   installed files are never overwritten. For library integration use
   `uv add git+https://github.com/raddl3/raddle@v0.4.1`. Your project needs Python 3.12+; pin it with
   `uv python pin 3.12` if needed. On Linux CUDA 12, install the backend with
   `uv add "raddle[cuda12] @ git+https://github.com/raddl3/raddle@v0.4.1"`. The optional kickoff text is also installed in `KICKOFF.md`.
2. **Lock one target, then profile.** A prompt such as "Use Raddle on the inference
   path" is enough. The skill traces the named invocation and proposes one target:
   representative case, objective, boundary, trusted reference, included/excluded
   paths and compute constraints. It asks "Is this the workload you want accelerated?"
   and stops for approval before profiling, model downloads, credentials or candidates.
   Unreachable legacy/archived/experimental paths stay excluded. After approval,
   run trusted tests and profiling only within that boundary. Distinguish measured
   hotspots from static inspection. Credentials, model downloads and data transfers
   require explicit approval in their own right.
   Record `AccelerationTarget` in `ForgeContract(..., target=target)` using the
   [public integration guide](external-workload.md). The recommended local ledger
   is `.raddle/campaigns/<id>/forge.jsonl`, alongside candidates and artifacts;
   it contains the inspectable target/hash. Ignore generated state in Git unless
   deliberately preserving sanitized evidence. Changed scope needs a new approved
   target and campaign. Historical campaigns are readable without rewriting them.
3. **Review the acceleration plan.** Before candidate edits, review the proposed
   change, semantics, tolerances, cases, timing boundary (including setup and
   transfers), compute, and exact commands. Static inspection and GPU paths
   without GPU measurements must be labeled **unmeasured**. No numerical GPU
   speedup estimates. If no adapter exists, use the [external integration guide](external-workload.md)
   and [complete example](../../examples/external-workload/README.md) to define
   the reference and workload-owned Forge callbacks as part of the approved plan.
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

Use the workload's Forge callbacks, implementing the small
[public callback contract](external-workload.md) when the adapter is missing. Forge builds and validates candidates
against the reference before it permits benchmarking. Compare the same workload
and state the timing boundary and environment. Built-in `raddle verify` and
`raddle benchmark` cover their own canonical cases; their receipts do not prove
correctness or speedup for your project.

Review validation, provenance, raw timings, and reproduction commands. Failed or
unmeasured candidates cannot become accepted GPU results. Use `create_external_artifact` for the accepted incumbent, following the
[packaging example](../../examples/external-workload/README.md) and verify it with
`raddle.artifact.read_artifact`. Packaging requires the existing artifact
contract, including source/package identities and evidence; it is not a generic
CLI command for arbitrary repositories. Adoption in the original project is a
separate user review, not an automatic merge.

To run the example from a public checkout, use `uv sync --frozen` and
`task example`. The pinned installation above includes the complete bundled skill.
