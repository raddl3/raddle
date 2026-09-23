# ADR-0001: Public product and private platform are separate repositories

- Status: Accepted
- Date: 2026-09-23

## Context

Raddle has two responsibilities.

First, it is an open-source acceleration product: accelerator contracts, reference and accelerated implementations, runtime behavior, validation, provenance, CLI behavior, and reproducible benchmarks.

Second, it may operate a commercial service: the public website, hosted execution, accounts, scheduling, infrastructure providers, billing, deployment integrations, and other service concerns.

A single public/private monorepo would make the visibility boundary procedural rather than structural. Splitting every component into its own repository would create coordination overhead before the product warrants it.

## Decision

Use two repositories inside one local workspace.

### `raddle` — public

Owns:
- Python package and CLI
- accelerator contract
- runtime
- reference adapters
- accelerated implementations
- validation
- provenance
- reproducible benchmark definitions and receipts
- examples and public technical documentation

Accelerators remain modules/packages in this repository until independent release/versioning pressure is real.

### `raddle-platform` — private

Owns:
- `raddle.eu`
- hosted UI
- hosted API/control plane
- authentication/accounts
- scheduling/provider integration
- commercial deployment automation
- billing/usage systems when needed
- private product and brand documentation

The initial platform is a small application, not a fleet of microservices.

## Dependency rule

`raddle-platform` may depend on `raddle`.

`raddle` must not depend on `raddle-platform`.

The public package remains useful on local, customer-owned, HPC, and cloud hardware without contacting Raddle services.

Local development may use a path/editable dependency. CI and deployed environments use a released version or immutable source/image identity.

## Consequences

Benefits:
- enforceable open-source boundary,
- hosted execution can prove it uses the public product,
- exact public implementation can be recorded in run provenance,
- agents can reason across both repos from one parent workspace.

Costs:
- public contract changes can require coordinated PRs,
- local tooling must support two Git roots,
- cross-repo compatibility must be tested deliberately.

These costs are accepted.

## Rejected alternatives

### One public/private monorepo
Rejected because visibility and dependency boundaries would depend on convention and selective publishing.

### Repository per accelerator
Rejected because contracts and runtime conventions are not stable enough to justify independent repositories and release pipelines.

### Separate site, API, executor, runtime, and benchmark repositories
Rejected as premature operational complexity.

## Follow-up ADR triggers

Write a new ADR before:
- extracting an accelerator into an independently versioned project,
- introducing native Python extension build tooling,
- introducing a dedicated execution worker service,
- changing the public validation contract,
- changing the open-source license.
