# Raddle

Raddle keeps a reference computation visible while validating an accelerated
path against it. Its first product accelerator, `orbit.two_body_rk4`, propagates
independent Cartesian two-body trajectories with the same RK4 method in a
legible scalar Python reference, a NumPy-vectorized CPU candidate, and an
optional CuPy CUDA candidate.
`stats.bootstrap` applies the same contract to deterministic bootstrap means,
returning the full replicate distribution and percentile interval from a
shared chunked resampling plan.

Raddle is currently distributed from public Git, not PyPI. Install the pinned
public tool with Python 3.12, then initialize from your existing project root:

```sh
uv tool install --python 3.12 git+https://github.com/raddl3/raddle@62ce3c025c747f4793b2a3bd373c8c1afa81815b
raddle agent init
```

This installs the provider-neutral Raddle acceleration skill. Inspect a trusted workload,
review the acceleration plan, then let a coding agent or engineer build an
isolated candidate worktree. Source and data stay in your environment; no
upload to Raddle is required. The kickoff prompt is optional guidance.
Codex uses `.agents/skills/`; Claude Code uses `.claude/skills/`. Use
`--agent claude` or `--agent codex` when both are present, `--target PATH` to
name a project root, and `--dry-run` to preview files. Existing modified skill
files are never overwritten. For direct Python library use, run:

```sh
uv add git+https://github.com/raddl3/raddle@62ce3c025c747f4793b2a3bd373c8c1afa81815b
```

The project must use Python 3.12 or newer; use `uv python pin 3.12` if needed.
See [the project onboarding guide](docs/guides/accelerate.md) for local GPU,
existing SSH GPU, and no-GPU paths, and the
[proposed SSH executor design](docs/guides/ssh-evaluation.md).

```sh
uv sync --frozen
uv run --frozen raddle --version
uv run --frozen raddle list
uv run --frozen raddle inspect orbit.two_body_rk4 --json
uv run --frozen raddle verify orbit.two_body_rk4 --case circular.small --json
uv run --frozen raddle benchmark orbit.two_body_rk4 --case batch.standard --repeat 5 --warmup 1 --json
uv run --frozen raddle verify stats.bootstrap --case bootstrap.small --json
uv run --frozen raddle benchmark stats.bootstrap --case bootstrap.standard --baseline numpy.vectorized --repeat 5 --warmup 1 --output local-bootstrap.json
task evidence
task ci
```

Stage 1 artifact packaging uses the built-in orbit workload as a **fixture**, not
customer validation. Build the public wheel, then measure its scalar reference,
validate the NumPy candidate, benchmark both paths, and bundle the wheel with
raw evidence:

```sh
task build
uv run --frozen raddle artifact --case circular.small --wheel dist/raddle-0.3.0-py3-none-any.whl --output orbit-fixture-artifact
uv run --frozen python -c 'from pathlib import Path; from raddle.artifact import read_artifact; print(read_artifact(Path("orbit-fixture-artifact")).to_json())'
```

The artifact directory contains `manifest.json`, `benchmark.json`, and the
wheel. The manifest records the reference baseline before candidate execution;
the benchmark receipt contains separate paired baseline/candidate timings,
validation results, tolerances, workload, timing scope, and environment. The
wheel digest pins executable bytes. Run the manifest's first command from the
artifact directory to repeat the baseline, validation, and measurement on
another host; nanosecond timings will differ.
See [the artifact contract](docs/concepts/accelerator.md).

On a Linux CUDA 12 host with a compatible NVIDIA driver, install the optional
backend and its CUDA components from the same pinned public source:

```sh
uv add "raddle[cuda12] @ git+https://github.com/raddl3/raddle@62ce3c025c747f4793b2a3bd373c8c1afa81815b"
```

`raddle inspect orbit.two_body_rk4` distinguishes
supported implementations from those available on the current host. Select
the GPU with `--implementation cupy.vectorized`. For benchmarks, choose
`--timing-scope end_to_end` (the default, including GPU transfers) or
`--timing-scope compute_only` (device-resident work), and optionally
`--baseline numpy.vectorized` to compare against the CPU vectorized path.

`raddle inspect`, `verify`, and `benchmark` support `--json`. Validation emits
an independently versioned receipt with implementation IDs, case, float64
tolerances, comparison diagnostics, and allowlisted execution provenance.
`benchmark` validates before timing and emits a separate versioned receipt
with individual timings, medians, synchronization, scope, transfer policy, and
the computed same-scope ratio. A local measurement is not a portable
performance claim. See [ADR-0003](docs/architecture/ADR-0003-gpu-benchmark-semantics.md)
for the asynchronous timing boundary.

Published receipts live in `src/raddle/receipts/` and are checked in CI.
They are measured evidence; any displayed claim must be derived from a valid
committed receipt with its workload, scope, hardware, and validation context.
See [ADR-0004](docs/architecture/ADR-0004-bootstrap-and-published-evidence.md).

The old `fixture.sum_squares` was only a bootstrap test fixture and is not a
product accelerator. The contract decision is recorded in
[ADR-0002](docs/architecture/ADR-0002-accelerator-contract.md).

The project uses Python 3.12, uv, Ruff, strict mypy, pytest, Bandit, Trivy,
Taskfile v3, Commitizen, prek, and Lefthook. `task bootstrap` installs locked
Python dependencies and Lefthook's Git hooks. Install the standalone
`lefthook`, `prek`, `trivy`, and `task` CLIs before running it. Lefthook is the
only hook installer; `prek install` is never used.

# External workloads

The independent [`raddle-workload-ssapy`](../raddle-workload-ssapy) repository
is the Stage 2 example. From that repository, `task artifact` measures LLNL
SSAPy's pinned RK4 reference, validates the Raddle candidate, and then
benchmarks it. The smoke case is small enough for CI:

```sh
uv run --frozen raddle-ssapy artifact --case ssapy.leo.smoke --output artifact
```

The resulting schema 2 bundle records the external case, source and wheel
identities, tolerances, baseline, profile summary, environment, dependencies,
lockfile, and benchmark receipt. The shared
`raddle.artifact.read_artifact(Path("PATH"))` reader checks its hashes and
identities without registering the external workload in Raddle.

That workload also includes Forge v0, a manual candidate ledger. Create a
reference baseline before editing `candidate.py`, run each candidate against
that parent, and explicitly accept or reject its evidence:

```sh
uv run --frozen raddle-forge baseline --id leo-base --case ssapy.leo.campaign
uv run --frozen raddle-forge run --id trial-1 --parent leo-base --case ssapy.leo.campaign --hypothesis "Describe one change"
uv run --frozen raddle-forge decide trial-1 --accept
uv run --frozen raddle-forge winner
```

Forge stores the append-only experiment ledger and checked artifacts in the
workload repository's current directory. Failed validation has no benchmark and
cannot be selected as a winner.
