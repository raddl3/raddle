# ADR-0005: Fused deterministic bootstrap on CUDA

- Status: Accepted
- Date: 2026-09-24

## Context

At 256 observations and 65,536 replicates on an A100, the original end-to-end
CuPy path spent about 372 ms constructing the deterministic plan on the CPU and
38 ms transferring indices. GPU gather and mean took about 4 ms. Moving the
plan to CuPy uint64 operations reduced generation to about 4 ms, but still
materialized index chunks that the result does not need.

## Decision

`stats.bootstrap` retains `splitmix64.counter_reject.v1`, its row-major
counter positions, uint64 wraparound, rejection threshold, full float64 result,
and validation policy. The CuPy implementation version advances to 2. A
CuPy RawKernel fuses each replicate's deterministic draws, sample lookup, and
mean reduction. It holds only the sample and output distribution on device;
index matrices are not allocated. The same counter and rejection rules remain
available as a CuPy uint64 plan generator for direct equivalence tests.

A zero rejected draw is remixed after replacing it with the SplitMix64
increment constant. Zero was a fixed point of the previous retry rule and
would never have returned a result; all previously terminating draws are
unchanged. CPU and both GPU paths use this rule identically.

`compute_only` for the fused GPU path now includes device-side plan generation
inside the kernel and excludes sample/result host transfers and host summary.
`end_to_end` includes all transfers and the host summary. Both scopes
synchronize the current CUDA stream before and after timed calls. The NumPy
path continues to generate the same bounded plan, using in-place uint64
operations to avoid unnecessary temporary arrays. The scalar Python path
remains the semantic reference.

## Consequences

No backend-specific RNG, native extension build, or new dependency is needed.
The kernel reduces values in parallel, so float64 rounding can differ from
the scalar reference; the existing elementwise validation policy remains the
gate. Performance evidence must compare full same-scope paths, identify the
workload and hardware, and validate before timing.
