# Accelerate an existing project

Raddle comes to your repository. Source code and workload data stay in your
environment; no upload to Raddle is required. A coding agent or engineer
inspects the project and creates candidates. Initialization installs guidance,
not an autonomous optimizer or a workload discovery service.

1. **Set up and start.** Install the pinned public tool in your existing repository:

   ```sh
   uv tool install --python 3.12 git+https://github.com/raddl3/raddle@v0.6.0
   raddle init
   raddle start
   ```

   Setup detects Codex and Claude Code on PATH. Choose a runtime, then inherit its
   existing model backend/authentication or select supported overrides. The next
   action offers a guided session or exit. The session asks whether to describe a
   workload or inspect the project. Normal agent trust, authorization and sandbox
   settings remain in effect. `start` requires a terminal; it never uses headless
   agent execution or starts profiling itself.

   Codex skills install in `.agents/skills/raddle-accelerate/`; Claude Code skills
   install in `.claude/skills/raddle-accelerate/`. Existing `raddle agent init
   --agent ...` remains a skill-only installer. It does not create launch settings.

   Script equivalent:

   ```sh
   raddle init --non-interactive --agent codex --backend default
   raddle doctor --json
   raddle start --dry-run
   ```

   Use `--target PATH` for an explicit project root. Guided commands use the current
   directory by default, so run them at the intended repository root. `init --dry-run`
   writes nothing. `start --dry-run` prints a JSON argument array without launching.
   Inspect `.raddle/agent.json`; changing choices requires `init --reconfigure`.
   Omitted noninteractive choices preserve existing choices for the same runtime;
   `--model default --effort default` clears overrides. CLI launch overrides take
   precedence over native runtime settings; empty values inherit them. The file
   accepts only agent/backend/model/effort, never keys, endpoints or arbitrary flags.
   Ignore generated campaigns according to project conventions; keep reviewed
   launch configuration if useful. Setup does not edit your Git ignore or app files.

   Supported combinations:

   | Runtime | Backend | Model override | Effort override |
   | --- | --- | --- | --- |
   | Codex | Existing runtime configuration (`default`) | Exact identifier in the runtime's local `models_cache.json` catalog | low/medium/high when that explicit catalogued model declares support |
   | Claude Code | Existing runtime configuration (`default`) | Inherit runtime model; explicit overrides unsupported | low/medium/high if installed CLI exposes `--effort`; model must support it |

   Codex overrides use `--model` and `--config model_reasoning_effort=...`.
   Claude effort uses `--effort`. Native runtime catalogs/settings are authoritative;
   no Raddle model catalog or hardcoded model default exists. A cached listing is
   not a live availability/authentication check: the runtime rejects inaccessible
   models/settings at launch. Raddle never adds a fallback model/provider.
   Missing catalog? Select the model in Codex first, or inherit runtime default.
   Unverified identifiers, including arbitrary capitalization, are rejected.

   Explicit `--backend openrouter`, `ollama`, `lmstudio`, and custom endpoints are
   unsupported in v0.6.0. Existing native backend configuration may be inherited;
   Raddle does not verify third-party routing compatibility and cannot promise it
   works. Configure and test it directly in the runtime before selecting default.
   No provider authentication/configuration is copied into the project.

   Interfaces were checked against installed CLI help and the official
   [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
   and [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference).
   Older runtimes without required flags fail explicitly.

2. **Lock one target, then profile.** A prompt such as "Use Raddle on the inference
   path" is enough. The skill traces the named invocation and proposes one target:
   representative case, objective, boundary, trusted reference, included/excluded
   paths and compute constraints. It asks "Is this the workload you want accelerated?"
   and stops for approval before profiling, model downloads, credentials or candidates.
   Unreachable legacy/archived/experimental paths stay excluded. After approval,
   run relevant preflight, then trusted tests and profiling only within that boundary. Distinguish measured
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

## Preflight and approvals

`raddle doctor` provides concise checks; `--json` returns `blocked` and a `checks`
array. Exit 1 means a required check is BLOCKED; exit 2 means invalid usage.
PASS verifies the named requirement; WARN is a concern; NOT CHECKED means no
verification and must not be treated as a pass. General checks cover the tool's
Python/OS/version, runtime/launch config, worktree, access flags and conflicting
virtualenv/Conda activation. Authentication and backend availability are NOT CHECKED.
CPU projects never require CUDA. No remediation is automatic.

After target approval, the agent requests only relevant workload checks:

```sh
raddle doctor --workload-approved --device cpu --tool uv --min-free-bytes 1048576 --json
raddle doctor --workload-approved --device cuda:0 --framework onnxruntime \
  --python /path/to/project/.venv/bin/python \
  --artifact models/model.onnx=APPROVED_SHA256 --json
```

Supply actual approved hashes. Artifact paths resolve inside the project boundary;
files are streamed, not loaded as models. Scratch access/free space can be checked
with `--scratch PATH --min-free-bytes N`. Explicit framework probes run fixed,
bounded isolated imports in the trusted workload interpreter, with bytecode writes
disabled. Review installed dependencies before importing them: third-party import
code is outside Raddle's control. No application command, tensor/model loading,
download, credentials, environment repair or transfer is performed.

GPU driver visibility/provider discovery does not prove library/session execution,
exclusive access or benchmark readiness. These remain NOT CHECKED. The agent must
verify required gaps with approved lightweight workload tests before expensive
profiling/evaluation, including temporary config and harness dependencies. BLOCKED
stops work depending on it. Changes to dependencies, configuration, permissions or
data need approval. `--workload-approved` declares an already approved target;
it does not replace approval evidence or the immutable Forge target.

At target, plan, adoption and next-loop decisions the agent offers **Approve /
Request changes / Decline**. It uses native questions only when the active mode
actually exposes a suitable tool; otherwise it asks conversationally. Failed tool
calls, defaults, silence and ambiguous replies never authorize execution. Request
changes collects instructions, revises the proposal, then requires fresh approval.
Decline stops the proposed action and preserves existing evidence.

## Upgrade from v0.5.0

Upgrade the pinned tool, then run `raddle init`. Existing Forge targets, contracts,
ledgers, artifacts and loop lineage need no migration. Skill-only users can keep
using their agent and the installed skill without `start`.

A differing installed skill is protected even if it came from an older Raddle
release. Compare it with `raddle agent init --target /path/to/empty-review-directory`
to review the new bundle. Back up and deliberately move the old installed skill
folder after review, then rerun `raddle init`; merge your custom instructions by
hand. `--reconfigure` changes launch choices only and never overwrites skill files.
No historical campaign or evidence is rewritten.
