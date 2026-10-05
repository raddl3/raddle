# Approved ML inference workloads

Read only after target lock. Separate cold initialization, warm invocation and
steady-state throughput. Identify whether process/container initialization,
model loading/session creation, preprocessing, H2D, model execution, D2H and
postprocessing fall inside the approved boundary. Measure included stages and
end-to-end time; synchronize asynchronous device work at timing boundaries.
Do not move work out of the boundary to manufacture an improvement.

Inspect where relevant:

- actual execution providers, node placement and fallback to CPU;
- runtime/session options, thread pools, device selection and graph optimization;
- dynamic/static shapes and actual input distributions;
- batching, queues and throughput versus per-request latency constraints;
- preprocessing parallelism and CPU/device overlap;
- IO binding, reusable device buffers and avoidable H2D/D2H round trips;
- launch overhead, operation/kernel fusion and CUDA graphs, including capture
  compatibility, address/shape stability and state/replay correctness;
- compatible runtimes such as ONNX Runtime, TensorRT or framework compile paths:
  supported operators, fallback, build/compile cost, cache identity and amortization;
- precision changes under the approved tolerances, including sensitive cases;
- persistent model/session state and lifecycle/invalidation semantics.

These are investigation categories, not mandatory candidate attempts. Select
hypotheses using [opportunities.md](opportunities.md) and measured evidence.
Validate all externally relevant outputs, dtype/shape, preprocessing/postprocessing,
state and error behavior; use task-specific acceptance criteria where needed.

For a local GPU campaign, repository-pinned model artifacts (record content hashes)
and explicitly recorded inference settings can define the trusted reference.
Do not demand exact cloud-production parity unless cloud/orchestration belongs to
the approved target. Record hardware/software/settings and keep claims limited to
that execution. Model downloads, credentials and data transfers need explicit
approval; absence of suitable compute leaves GPU hypotheses unmeasured.
