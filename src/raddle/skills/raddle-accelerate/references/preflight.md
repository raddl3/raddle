# Readiness before expensive work

General: `raddle doctor --json`. The tool environment differs from the application's
locked environment. Diagnose BLOCKED setup checks; do not install/repair automatically.
Legacy skill-only installs have no launch config: use `raddle init` for guided launch,
or verify the already running agent and document that setup-only blocker.

After explicit target approval, inspect its invocation, dependency lock, configuration,
compute selection and model/input identities. Request only relevant checks:

```sh
raddle doctor --workload-approved --device cpu --tool uv --json
raddle doctor --workload-approved --device cuda:0 --framework onnxruntime \
  --python /path/to/workload/.venv/bin/python \
  --artifact models/model.onnx=APPROVED_SHA256 --min-free-bytes 1073741824 --json
```

`--workload-approved` declares prior human approval; it does not grant consent or
replace `AccelerationTarget`. Artifact paths stay inside the approved project.
Hashes stream local files, never load models. Framework probes use the explicit
trusted interpreter with isolated imports, no bytecode writes, no model/tensor
loading, and a timeout. Review third-party import behavior before invoking a probe.
General checks do not import frameworks, require CUDA, inspect credentials or call
providers. No application benchmark command is run. The tool never repairs state.

PASS verifies the named narrow check only. Permissions use access flags without
creating test files. GPU driver visibility and advertised framework providers do
not prove CUDA libraries/session creation work. NOT CHECKED identifies this gap.
Within the approved target, use an existing lightweight test for library loading,
actual device/provider placement, temporary configuration requirements and harness
dependencies. Check command working directories and the approved benchmark boundary.
Do not load large models, use credentials, download artifacts or transfer data
without separate authorization. Imports may initialize device runtime state;
do not claim they establish throughput, exclusive access or numerical correctness.

BLOCKED stops work requiring that capability. Offer a concrete remedy and obtain
approval before dependency/configuration/permission/data changes. WARN needs a
short assessment. NOT CHECKED is not PASS: establish required capabilities or
stop with the limitation. GPU absence does not block an approved CPU workload.
Preserve concise results alongside later evidence without secrets/private paths.
