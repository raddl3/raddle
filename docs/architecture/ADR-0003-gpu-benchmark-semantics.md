# ADR-0003: Optional CUDA candidate and synchronized benchmark scopes

- Status: Accepted
- Date: 2026-09-24

## Context

`perf_counter_ns` measured synchronous NumPy calls correctly, but a CuPy call
can return before queued GPU work completes. Timing only that enqueue would be
false performance evidence. The same accelerator must describe and validate
both CPU and GPU candidates without requiring CUDA in the base installation.

## Decision

`orbit.two_body_rk4` keeps `python.scalar` as its reference and
`numpy.vectorized` as its default candidate. Its descriptor now lists all
candidate identities, including `cupy.vectorized`. The old `candidate`
attribute and JSON field remain aliases for the default NumPy candidate.
`cupy.vectorized` is supplied by the Linux CUDA 12 `cuda12` package extra,
which selects `cupy-cuda12x[ctk]` so NVRTC and matching CUDA components are
present on driver-only hosts. Ordinary installation remains CPU-only. The public registry reports whether
each supported implementation is available on the current host. It does not
hide import or CUDA failures behind a generic test skip.

Validation still compares the final host float64 state array against
`python.scalar` using `float64.state_elementwise.v1`. Its receipt schema moves
independently to v2 to add an optional, allowlisted GPU provenance object:
model, GPU count used, CuPy version, and CUDA runtime/driver version integers.
No host or device serial number is collected.

Benchmark receipt schema v2 names the candidate and the timed CPU baseline.
The default baseline remains `python.scalar`; `numpy.vectorized` can be used
to study the GPU crossover. Validation always uses `python.scalar`, regardless
of which baseline is timed. Both timed paths have the same declared scope.

`end_to_end` is the default and the future customer-facing comparison. The
caller supplies a validated host `PropagationInput` and waits for a final host
array. For CuPy, the timed call includes host-to-device conversion, RK4, the
final finite check, and device-to-host conversion. `compute_only` starts with
the input already on the GPU and ends with the output on the GPU. It excludes
bulk host/device transfers and the final host-visible finite check; a full
validation is completed before any timing. The receipt labels the scope and
whether host/device transfers are included. CPU paths have no such transfers.

Case construction, CUDA context creation, and first-use kernel compilation
are setup and are excluded from both scopes. Warmup runs are separate and
excluded from measured repetitions. Each measured CuPy call uses a current-
stream barrier before and after `perf_counter_ns`; the post barrier completes
queued work before the clock stops. Synchronous CPU calls need no barrier.
Receipts record the clock, both synchronization policies, warmup and repeat
counts, individual durations, medians, and the same-scope baseline/candidate
ratio. A ratio without its scope, baseline, transfer rule, and validation is
not publishable evidence. No performance threshold belongs in ordinary CI.

The package choice follows the [CuPy CUDA 12 wheel documentation](https://docs.cupy.dev/en/stable/install.html)
and [uv optional-dependency documentation](https://docs.astral.sh/uv/concepts/projects/dependencies/).
The synchronization rule follows [CuPy's performance guidance](https://docs.cupy.dev/en/stable/user_guide/performance.html).

## Deferred

No general backend interface, scheduler, multi-GPU execution, CUDA graph,
custom kernel, hosted GPU execution, or checked-in machine benchmark claim.
The static web catalog shows supported implementations and install route; it
does not claim that a viewer has a CUDA device. The platform API may report
availability only for its own host.
