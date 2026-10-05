# ADR-0008: Approved workload identity in Forge

Status: Accepted

## Context

Repository-wide discovery can optimize legacy paths unrelated to the user's
objective. The bundled skill needs an explicit workload approval boundary, and
Forge needs to reject changed workload scope when a campaign is resumed.

## Decision

The skill traces one execution path, proposes a target and stops for user approval
before profiling, downloads, credentials or candidate work. Profiling then informs
a separately approved plan. Focused references supply reusable investigation
knowledge without mandating optimization attempts or predicted speedups.

A frozen `AccelerationTarget` contains only immutable identity/evidence strings
and tuples. `ForgeContract` accepts an optional trailing target for API compatibility.
Target-bound contracts serialize its complete content and canonical JSON SHA-256;
Forge checks the contract during use and on reopening. Approval evidence is supplied
by the caller; Forge does not authenticate user consent or restrict execution.

When target is absent, serialization retains the historical shape. Existing
callers and ledgers remain usable, without migrations. New skill-led campaigns
must supply the approved target. Changing or retrofitting a target requires a new
campaign. Existing benchmark, validation, budget and incumbent behavior remains.

Recommend `.raddle/campaigns/<id>/` with the ledger, candidates and artifacts.
The ledger holds the inspectable target/hash; no second authoritative target file
or campaign manager is introduced. Keep secrets and large inputs outside state.
The existing Accelerator artifact schema stays unchanged; retain its campaign
ledger alongside it to preserve target evidence.
