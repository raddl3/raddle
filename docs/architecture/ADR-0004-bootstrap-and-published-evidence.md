# ADR-0004: Deterministic bootstrap and published benchmark evidence

- Status: Accepted
- Date: 2026-09-24

## Context

Orbit's state-vector case schema and validation policy cannot describe a
stochastic resampling workload. A seed shared between NumPy and CuPy does not
guarantee the same random draws. Local A100 observations also need a durable,
machine-generated receipt before they can support a product claim.

## Decision

`stats.bootstrap` v0.1 accepts a finite, nonempty float64 vector, at least two
resamples, a uint64 seed, a confidence level in `(0, 1)`, and only the arithmetic
mean. The result contains the complete float64 bootstrap distribution, original
mean, sample standard error (`ddof=1`), and a linear percentile interval. One
float64 per replicate is small enough for the canonical cases; retaining it
allows exact experiment inspection and elementwise validation. The largest
canonical case stores 512 KiB of replicate means.

The algorithm identity is `splitmix64.counter_reject.v1`. Each row-major index
position is mixed with the uint64 seed using fixed SplitMix64 arithmetic.
Values that would bias modulo for the sample size are re-mixed until accepted.
Every implementation evaluates these same indices. Chunk boundaries do not
change the logical stream, even across NumPy versions. The
index limit is 1,048,576 entries per chunk (8 MiB), so the full index matrix
is never built for end-to-end execution. The largest compute-only case stages
128 MiB of indices on the GPU before timing; that mode explicitly excludes
plan generation and transfer, while end-to-end includes both. CPU compute-only
also evaluates a staged host plan. Changing the plan algorithm or percentile
rule requires an accelerator version change.

`python.scalar` loops through rows and arithmetic means; `numpy.vectorized`
and optional `cupy.vectorized` evaluate the identical plan. The policy
`float64.bootstrap_distribution.v1` checks every replicate mean and derived
result with `1e-12` absolute and relative tolerance. This accommodates float64
reduction order only; it does not accept distributional similarity between
different random experiments. Independent constant and tiny-sample tests check
semantics outside the candidate/reference comparison.

Benchmark receipt schema v3 adds the complete canonical workload descriptor.
`raddle benchmark --output` writes canonical JSON intentionally. Committed
receipts live under `src/raddle/receipts/<accelerator-id>/`, allowing the
installed public package and the platform to read the same evidence. CI checks
the schema, exact canonical case and implementation identities, validation
status, timing arithmetic, provenance allowlist, and canonical serialization.
The receipt includes a SHA-256 content digest to detect accidental edits; it
is not an authenticity signature. No generation timestamp is used because it
would add nonmeasurement variability without improving interpretation.

A **benchmark receipt** is measured evidence from public Raddle machinery. A
**benchmark claim** is a presentation derived from a checked committed receipt,
with its workload, baseline, candidate, hardware, timing scope, and validation
context. A receipt describes the measured host and workload, not a universal
speedup. No CI performance threshold is introduced.

## Compatibility

Benchmark schema v2 remains readable as historical CLI output but cannot be
committed under the v3 evidence convention. Validation schema v2 remains
unchanged. `AcceleratorDescriptor` gains a typed bootstrap case variant and
optional algorithm ID; existing orbit metadata remains valid. The public
package version advances to 0.3.0, and the platform consumes that version.

## Deferred

No callback statistic system, configurable RNG, streamed result contract,
larger than canonical compute-only staging, or hosted execution.
