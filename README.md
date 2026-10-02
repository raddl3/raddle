# Raddle

**Keep the calculation. Lose the wait.**

Raddle is a validation and performance-engineering harness for trusted numerical
workloads. It helps a coding agent or engineer inspect a workload, test alternative
execution paths, reject incorrect candidates, and package accepted results with
reproducible evidence.

## Start in your existing repository

Raddle is distributed from public Git, not PyPI. With [uv](https://docs.astral.sh/uv/):

```sh
uv tool install --python 3.12 git+https://github.com/raddl3/raddle@8eeb7db8c8522a692c9ae4d5477d1f1be75da272
raddle agent init
```

Codex and Claude remain the candidate producers; Raddle supplies the harness.
Initialization installs a provider-neutral skill in `.agents/skills/` or
`.claude/skills/`. Choose `--agent codex` / `--agent claude`, use `--target PATH`,
or preview with `--dry-run`. Modified installed files are never overwritten.
Source and data stay in your environment.

**Inspect → Plan → Build → Forge → Artifact**

1. **Inspect:** profile your existing workload and preserve its reference.
2. **Plan:** agree on semantics, validation cases, timing boundaries, and compute.
3. **Build:** create an isolated candidate; define workload-owned callbacks.
4. **Forge:** build, validate, then benchmark. Record every experiment and retain
   only an eligible improvement as incumbent.
5. **Artifact:** package the accepted implementation, inputs, wheels, lockfile,
   validation, raw timings, and provenance; verify readback.

Follow the [project guide](docs/guides/accelerate.md) or run the complete
[external-workload example](examples/external-workload/README.md).

## Measured acceleration. Checked against the reference.

| Recorded case | Result | Evidence |
| --- | --- | --- |
| NPBench Jacobi 2D, medium case, NumPy reference → CuPy, A100 | **23.11×** end-to-end, transfers included | [Campaign and provenance](https://raddle.eu/campaigns/npbench-jacobi) |
| KernelBench level 2 Conv2D + ReLU + Bias, pinned PyTorch reference → candidate, A100 | **~1.37×**, device-only timing; upstream validation passed | [Campaign and provenance](https://raddle.eu/campaigns/kernelbench-conv2d) |

These are results for the recorded benchmark cases, not predictions for your
project. Campaign timings and separately packaged artifact measurements retain
their own evidence and timing scope.

## The public Python harness

For library use in an existing Python 3.12+ project:

```sh
uv add git+https://github.com/raddl3/raddle@8eeb7db8c8522a692c9ae4d5477d1f1be75da272
```

- [`ForgeContract` / `ForgeCampaign`](src/raddle/forge.py): immutable campaign
  identities, source snapshots/hashes, validation-before-benchmark gating,
  experiment ledgers, resume, and incumbent selection.
- [`BenchmarkResult`](src/raddle/forge.py): workload-owned evidence, score, and
  eligibility; lower scores win. Agents and engineers supply candidates.
- [`create_external_artifact` / `read_artifact`](src/raddle/artifact.py): package
  and verify an accepted Accelerator with executable bytes and evidence.
- [Contracts](src/raddle/contracts.py) and [evidence checking](src/raddle/evidence.py):
  versioned validation/benchmark receipts, timing scope, and allowlisted provenance.

No plugin registry is needed: supply build, validate, and benchmark callbacks to
`ForgeCampaign.evaluate`. The [integration guide](docs/guides/external-workload.md)
shows the complete callback and accepted-artifact path using public APIs.

To run the complete example from the public checkout:

```sh
git clone https://github.com/raddl3/raddle.git
cd raddle
uv sync --frozen
uv run --frozen raddle agent init --target /path/to/your/project
task example
```

## Built-in accelerators and development

`orbit.two_body_rk4` and `stats.bootstrap` provide numerical examples with
inspectable reference, NumPy, and optional CUDA paths. They illustrate contracts;
the harness also integrates external workloads.

```sh
uv run --frozen raddle list
uv run --frozen raddle inspect orbit.two_body_rk4 --json
uv run --frozen raddle verify orbit.two_body_rk4 --case circular.small --json
uv run --frozen raddle benchmark stats.bootstrap --case bootstrap.small --json
task ci
```

[Documentation](docs/README.md) · [Artifact contract](docs/concepts/accelerator.md) ·
[Manual SSH evaluation](docs/guides/ssh-evaluation.md) ·
[Architecture and development history](docs/architecture/product-history.md)
