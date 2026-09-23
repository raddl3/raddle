# Raddle

Raddle keeps a reference computation visible while validating an alternate
execution path against it. This initial package contains only a non-product
fixture; it makes no acceleration claim.

```sh
uv sync --frozen
uv run --frozen raddle --version
uv run --frozen raddle list
uv run --frozen raddle verify fixture.sum_squares
task ci
```

`raddle verify` emits one stable JSON object per invocation. Its receipt records
the contract version, implementation IDs, case ID, runtime version, both
results, and validation outcome. The fixture's two Python implementations are
deliberately trivial.

Before a benchmark is published, its receipt must identify the reference and
accelerator versions, workload, hardware, software/runtime versions, timing
method, and validation result. No benchmark command or claim exists yet.

The project uses Python 3.12, uv, Ruff, strict mypy, pytest, Bandit, Trivy,
Taskfile v3, Commitizen, prek, and Lefthook. `task bootstrap` installs locked
Python dependencies and Lefthook's Git hooks. Install the standalone
`lefthook`, `prek`, `trivy`, and `task` CLIs before running it. Lefthook is the
only hook installer; `prek install` is never used.
