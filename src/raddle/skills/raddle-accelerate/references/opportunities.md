# Evidence-driven opportunities

Investigate only the locked execution path and objective. These are inspection
categories, not a requirement to attempt every optimization:

| Category | Evidence to look for |
| --- | --- |
| Repeated/unnecessary work | Duplicate computations, conversions, reloads, invariant work inside loops. |
| Batching/vectorization | Per-item overhead, small calls, legal aggregation under ordering/latency constraints. |
| Concurrency/parallelism | Independent CPU/preprocessing/IO work, serialization, oversubscribed thread pools. |
| Data movement / host-device transfers | Bytes and synchronization costs, round trips, copies between stages. |
| Allocation/reallocation / memory layout | Allocator overhead, temporary buffers, contiguity, strided access. |
| Launch overhead / kernel fusion | Many short operations, idle gaps, opportunities to combine operations. |
| Compiled execution | Interpreter/dispatch overhead, stable graphs/shapes and amortizable compilation. |
| Runtime/provider configuration | Actual provider placement, fallbacks, thread settings, graph options. |
| Vendor libraries | Existing compatible optimized implementations preserving the contract. |
| Persistent state/caching | Repeated initialization or invariant results; lifecycle and invalidation requirements. |
| Precision changes | Numerically expensive precision, permitted error budget and sensitive outputs. |
| Contract-preserving specialization | Proven fixed shapes/types/ranges; retain guards for the declared domain. |

Measure the baseline and profile first, using the same representative case and
boundary. Attribute costs before selecting hypotheses; static code review alone
cannot identify a measured bottleneck. Use existing tooling and installed libraries.

For EVERY proposed hypothesis state:

- measured bottleneck and evidence;
- mechanism that removes/reduces that cost;
- affected objective: cold latency, warm latency, throughput or another measure;
- correctness/semantic risk (ordering, state, concurrency, precision, input domain);
- required validation against the trusted reference and fixed policy;
- implementation scope, dependencies and commands within the approved target.

Do not invent expected numerical speedups. Propose only relevant hypotheses,
with an experiment budget; stop for user approval before candidate work.
