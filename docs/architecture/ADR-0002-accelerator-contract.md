# ADR-0002: Float64 accelerator contract and independent evidence receipts

- Status: Accepted
- Date: 2026-09-24

## Context

The bootstrap contract described one integer fixture. A scalar result and a
free-form validation string cannot describe batched float64 trajectories or
show how close an accelerated result is to its reference. The first product
accelerator is `orbit.two_body_rk4`.

## Decision

Keep a stable accelerator ID and semantic version, a human-readable input and
output and supported-environment descriptions, and deterministic JSON serialization. Keep the public
package as the sole owner of accelerator behavior and validation.

Change implementation fields to typed ID/version pairs. Describe canonical
cases with typed batch size, gravitational parameter, timestep, and step count.
The actual numerical input is a validated `(batch, 6)` float64 state array,
positive finite `mu` and `dt`, and a positive integer step count. The output
is a final `(batch, 6)` float64 state array. Inputs use consistent units;
Raddle does not impose a unit system.

Change validation to elementwise
`|candidate - reference| <= 1e-11 + 1e-10 * |reference|`. This policy is
identified as `float64.state_elementwise.v1`. The absolute term protects
near-zero components; the relative term scales with nonzero state values.
The validation receipt records match status, compared scalar count, maximum
absolute error, and maximum relative error. The relative diagnostic is taken
only where `|reference| >= atol/rtol = 0.1`, where the relative term dominates;
it is zero when no component is in that region. Both execution paths use the
same RK4 stages and timestep. The tolerance accommodates small floating-point
ordering differences without accepting a meaningful perturbation.

Change evidence into separate `ValidationReceipt` and `BenchmarkReceipt`
dataclasses. Both independently start at `schema_version: 1`; neither schema
version is the accelerator or package version. Validation never depends on a
clock. A benchmark validates before timing, records every warmup/repeat count
and measured nanosecond duration from `perf_counter_ns`, plus medians and the
median ratio. A failed validation cannot produce a successful benchmark
receipt. JSON is key-sorted and rejects non-finite numeric values.

Execution provenance is a typed allowlist: Python, Raddle, and NumPy versions,
OS, architecture, processor, and logical CPU count. Receipts include case and
implementation identities. No hostname, username, environment variable,
private path, or credential is collected.

## Deferred

No universal ODE, backend, device, scheduler, plugin, validation DSL, or
remote-execution contract. No claim that RK4 exactly conserves orbital
quantities. No benchmark threshold in CI and no published speedup from a
single local machine.

The integer sum-squares fixture is removed from the installable product
surface. The v0.1 fixture-shaped receipt has no migration shim because it was
only a bootstrap contract; the platform consumer changes with this ADR.
