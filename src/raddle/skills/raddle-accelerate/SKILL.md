---
name: raddle-accelerate
description: Trace and lock one approved workload, profile it, propose acceleration, and evaluate isolated candidates with Raddle Forge.
---

# Accelerate one approved workload

The coding agent or engineer produces candidates; Raddle supplies the harness.
Source and data stay in the user's environment. Use trusted project commands.

DISCOVER → TRACE EXECUTION PATH → PROPOSE TARGET → USER APPROVES TARGET
→ WORKLOAD PREFLIGHT → PROFILE → PROPOSE ACCELERATION PLAN → USER APPROVES PLAN
→ ISOLATED CANDIDATE WORK → FORGE EVALUATION → ARTIFACT
→ ADOPTION REVIEW → APPLY + VERIFY → OFFER NEXT LOOP

Welcome briefly: "I'm ready to help accelerate your project. Would you like to
 describe a workload, or have me inspect this repository?" Investigate useful
 entrypoints yourself; ask only for unresolved scope. Run `raddle doctor --json`
 for general readiness before target selection. Resolve BLOCKED setup checks
 before proceeding; do not repair the environment automatically.

## Human decisions

At target, plan, adoption and another-loop approval, inspect the tools actually
available in this interaction mode. Use a native structured question tool only
when it supports these choices and free-text revision instructions. For example,
Claude Code may expose AskUserQuestion; Codex question tools depend on mode.
Do not assume a tool exists from the runtime name. If unavailable, restricted to
another mode, or a tool call fails, ask conversationally with the same choices:
**Approve / Request changes / Decline**. Never draw fake native controls.

- **Approve:** explicit approval of the exact current proposal permits only that
  stage. Record sanitized decision evidence. Silence, a default selection,
  an empty/tool error response, and ambiguous replies are not approval.
- **Request changes:** collect instructions, revise the proposal and STOP for
  fresh approval. Changes never authorize execution of the old or new proposal.
- **Decline:** stop the proposed action cleanly and report preserved evidence.
  Do not discard previous results, apply a patch or start another loop.

Normal runtime authorization and sandbox rules still apply. Raddle cannot
 authenticate consent. Never invoke expensive commands based on a pending question.

## Workflow

1. Read project instructions and [scoping.md](references/scoping.md). Trace from
   the user-named entrypoint; propose one target with explicit exclusions. Ask
   **"Is this the workload you want accelerated?"** and STOP until approved.
   Do this before expensive profiling, model downloads, credential use or candidates.
2. After target approval, run relevant `raddle doctor --workload-approved --json`
   checks using [preflight.md](references/preflight.md). Inspect requirements from
   the approved path, not every installed framework. BLOCKED stops the affected
   work; WARN needs assessment; NOT CHECKED is not a pass. Resolve required
   unchecked capabilities with a lightweight, approved workload probe before
   profiling or Forge evaluation. Environment changes need separate approval.
   Recheck relevant requirements when compute, artifacts or dependencies change.
   Profile only the approved path and representative case. Consult
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

7. After adoption review is approved, apply the accepted patch and rerun workload
   validation and measurement. Confirm adopted source bytes match the accepted
   incumbent. Record the artifact with `campaign.record_artifact(artifact_path)`.
   Report the measured result and evidence location, then ask:
   **"Accepted candidate applied and verified. Would you like Raddle to re-profile
   the improved workload and start another acceleration loop against the new incumbent?"**
   STOP until the user explicitly opts in. Do not automatically start profiling.
8. If the user says no, finish cleanly with the final result and evidence location.
   If yes, preserve the previous campaign, ledger, snapshots and artifact unchanged.
   Measure the adopted incumbent anew as the performance baseline and re-profile
   the same approved workload. Inspect the NEW bottleneck distribution; propose a
   fresh plan and experiment budget and STOP for plan approval. Never reuse old
   measurements or blindly reuse the old plan. After approval, use `next_loop`
   with a new campaign ID and directory, fresh baseline/profile evidence, budget,
   adopted source and parent artifact. Keep the ORIGINAL trusted reference for
   correctness validation, including artifact validation; it is not replaced by
   the performance incumbent. Follow the callback guide for machine-readable lineage.
   Changed workload scope/objective/case/reference requires renewed target approval.
9. If no candidate was accepted or adoption was not verified, there is no adopted
   baseline for another loop. Report that result; trying another plan requires its
   own approval and campaign and is distinct from optimizing an adopted incumbent.
