# Raddle

Raddle keeps a reference computation visible while validating an accelerated
path against it. Its first product accelerator, `orbit.two_body_rk4`, propagates
independent Cartesian two-body trajectories with the same RK4 method in a
legible scalar Python reference and a NumPy-vectorized candidate.

```sh
uv sync --frozen
uv run --frozen raddle --version
uv run --frozen raddle list
uv run --frozen raddle inspect orbit.two_body_rk4 --json
uv run --frozen raddle verify orbit.two_body_rk4 --case circular.small --json
uv run --frozen raddle benchmark orbit.two_body_rk4 --case batch.standard --repeat 5 --warmup 1 --json
task ci
```

`raddle inspect`, `verify`, and `benchmark` support `--json`. Validation emits
an independently versioned receipt with implementation IDs, case, float64
tolerances, comparison diagnostics, and allowlisted execution provenance.
`benchmark` validates before timing and emits a separate versioned receipt
with individual timings, medians, and the computed ratio. A local measurement
is not a portable performance claim.

The old `fixture.sum_squares` was only a bootstrap test fixture and is not a
product accelerator. The contract decision is recorded in
[ADR-0002](docs/architecture/ADR-0002-accelerator-contract.md).

The project uses Python 3.12, uv, Ruff, strict mypy, pytest, Bandit, Trivy,
Taskfile v3, Commitizen, prek, and Lefthook. `task bootstrap` installs locked
Python dependencies and Lefthook's Git hooks. Install the standalone
`lefthook`, `prek`, `trivy`, and `task` CLIs before running it. Lefthook is the
only hook installer; `prek install` is never used.
