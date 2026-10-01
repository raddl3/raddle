# ADR 0007: External workload artifacts

Stage 2 keeps workload code in its owning repository. That repository calls
the reference implementation and candidate, supplies its case and comparison
policy, and asks Raddle to save evidence only after validation succeeds.

Schema 2 extends the existing artifact reader while preserving Stage 1's
schema 1. It bundles inputs, environment lock, both wheels, reference baseline,
benchmark receipt, source identities, and a short profile summary. Raddle does
not discover workloads, load plugins, or generate candidates.

The candidate source member may live in either bundled wheel. Its declared
package selects the wheel used to hash and verify those source bytes; this keeps
external candidate code in its owning workload repository without changing the
artifact schema.

The first consumer is `raddle-workload-ssapy`, which compares pinned LLNL
SSAPy RK4 propagation with Raddle's NumPy RK4 candidate. Additional generic
workload features require a demonstrated second use case.
