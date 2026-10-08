# Raddle

**Keep the calculation. Replace the execution.**

Raddle is a validation and performance-engineering harness for trusted numerical
workloads. It helps a coding agent or engineer inspect a workload, test alternative
execution paths, reject incorrect candidates, and package accepted results with
reproducible evidence.

## Start in your existing repository

Raddle is distributed from public Git, not PyPI. With [uv](https://docs.astral.sh/uv/):

```sh
uv tool install --python 3.12 git+https://github.com/raddl3/raddle@v0.6.0
raddle init
raddle start
```

`raddle init` detects installed Codex and Claude Code runtimes, installs the skill,
and stores inspectable launch choices in `.raddle/agent.json`. `raddle start` opens
your normal interactive agent with a short welcome: describe a workload or let it
inspect the project. No handcrafted kickoff prompt is needed.

Raddle supplies contracts, workflow and evidence; the coding agent produces
candidates. Your existing runtime backend/authentication stays in charge. Setup
never changes global agent configuration or stores credentials. Modified installed
skill files are never overwritten. Agent providers retain their normal data policies;
Raddle requires no source/data upload to a hosted Raddle service.

For scripts: `raddle init --non-interactive --agent codex` (or `claude`).
Run `raddle doctor --json` for read-only readiness checks and
`raddle start --dry-run` to inspect the exact launch arguments.
See the [setup guide](docs/guides/accelerate.md) for supported models/backends,
workload preflight, approval fallback and upgrading from v0.5.0.

**Discover → Trace → Target approval → Preflight → Profile → Plan approval → Build → Forge → Artifact**

1. **Target:** trace one execution path, lock inclusions/exclusions and ask
   "Is this the workload you want accelerated?" Stop until approved.
2. **Profile and plan:** measure only that target, propose evidence-based hypotheses,
   semantics, validation and compute; stop for plan approval.
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
uv add git+https://github.com/raddl3/raddle@v0.6.0
```

- [`AccelerationTarget` / `ForgeContract` / `ForgeCampaign`](src/raddle/forge.py): immutable campaign
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
