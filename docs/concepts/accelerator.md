# Accelerator contract

A product accelerator needs a stable ID and version, independently inspectable
reference and candidate implementations, declared input/output contracts, a
validation policy, execution provenance, and reproducible cases.

`orbit.two_body_rk4` is the first product accelerator. It takes one or more
finite float64 Cartesian states `[x, y, z, vx, vy, vz]`, positive `mu`, positive
`dt`, and a positive step count. Both paths apply fourth-order Runge-Kutta to
`dr/dt = v` and `dv/dt = -mu*r/||r||³`. The scalar `python.scalar` reference
steps trajectories one by one; `numpy.vectorized` steps a batch together.

`circular.small` supports fast validation and an independent near-one-period
circular-orbit sanity check. `batch.standard` exercises batching and is for
local measurement, never a CI speed assertion. Case inputs are deterministic,
without random seeds. The policy and receipt schemas are in
[ADR-0002](../architecture/ADR-0002-accelerator-contract.md). The former
`fixture.sum_squares` was test-only and is not registered as a product.
