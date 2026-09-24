# Accelerator contract

A product accelerator needs a stable ID and version, independently inspectable
reference and candidate implementations, declared input/output contracts, a
validation policy, execution provenance, and reproducible cases.

`orbit.two_body_rk4` is the first product accelerator. It takes one or more
finite float64 Cartesian states `[x, y, z, vx, vy, vz]`, positive `mu`, positive
`dt`, and a positive step count. Both paths apply fourth-order Runge-Kutta to
`dr/dt = v` and `dv/dt = -mu*r/||r||³`. The scalar `python.scalar` reference
steps trajectories one by one; `numpy.vectorized` steps a CPU batch together;
optional `cupy.vectorized` applies the same stages on a CUDA device. All
candidates use the same reference and float64 validation policy.

`circular.small` supports fast validation and an independent near-one-period
circular-orbit sanity check. `batch.standard` exercises batching and is for
local measurement, never a CI speed assertion. Larger deterministic batch
cases support CPU/GPU crossover measurement without random seeds. The initial
policy is in [ADR-0002](../architecture/ADR-0002-accelerator-contract.md),
and multi-candidate timing semantics are in
[ADR-0003](../architecture/ADR-0003-gpu-benchmark-semantics.md). The former
`fixture.sum_squares` was test-only and is not registered as a product.
