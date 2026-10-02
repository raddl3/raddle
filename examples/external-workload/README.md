# External workload integration

A deliberately small CPU example of the public harness, not a published
accelerator or performance claim. It squares a deterministic float64 sequence:
scalar NumPy calls are the reference; a batch NumPy call is the candidate.
This simple calculation keeps attention on integration rather than optimization.

From a fresh public checkout with Python 3.12 and uv:

```sh
uv sync --frozen
task example
```

`task example` builds the matching Raddle wheel and runs this locked example in
its own environment. It creates a fresh temporary campaign directory and prints
the artifact location. For a named output, from the repository root:

```sh
uv build --wheel
uv run --project examples/external-workload --python 3.12 --frozen python -m external_workload /tmp/my-square-campaign "$PWD/dist/raddle-0.4.0-py3-none-any.whl"
```

Use a new output directory each time. Timings depend on your machine; if the
candidate fails validation or does not improve the baseline, the ledger records
rejection and the example refuses to package it. No speed assertion is a claim
about another workload.

Read the three source files in order:

1. [`__init__.py`](src/external_workload/__init__.py): existing scalar reference.
2. [`candidate.py`](src/external_workload/candidate.py): independent candidate.
3. [`__main__.py`](src/external_workload/__main__.py): reference identity/case/policy,
   measured baseline and cProfile evidence, `ForgeCampaign`, snapshot build,
   exact validation, benchmark, incumbent selection, wheel packaging and readback.

The reference identity records installed NumPy's full upstream Git revision plus
this adapter's source hash. The case and policy are fixed in the ledger. Timing
includes allocations and all work from input rule to output; no GPU is involved.

The accepted source is loaded from Forge's snapshot, copied into a workload wheel
and checked byte-for-byte. `create_external_artifact` validates and measures a
separate run; `read_artifact` verifies the bundle and its agreement with the
incumbent. Inspect `ledger.jsonl`, `sources/`, and `artifact/manifest.json`,
`benchmark.json`, inputs, lockfile and wheels. Nothing is uploaded.

The manifest's command, run from `artifact/`, reexecutes reference/candidate
validation and prints fresh raw baseline/candidate measurements from the packaged
workload wheel, with pinned NumPy and the included Raddle wheel. The ledger retains the selection
measurements; rerun the complete example from the checkout to create new timing
evidence. Local paths/host identifiers are excluded from structured evidence.

The path dependency in this example's lockfile intentionally consumes the public
checkout. In your existing project, use an immutable public Raddle release and
supply your own callbacks. See the [callback and artifact guide](../../docs/guides/external-workload.md).
