# ADR-0010: Guided launch over existing agent runtimes

Status: Accepted

`init` installs the existing bundled skill and records only native launch overrides
in `.raddle/agent.json`; `start` launches the installed interactive Codex or Claude
binary using an argument array, inherited terminal/environment and normal native
permission settings. Runtime authentication, backend settings and model discovery
remain runtime-owned. No chat framework, global config changes, secret storage or
Raddle catalog is introduced. Explicit new provider routing is unsupported.

Codex model choices come from its local catalog. Claude model overrides are
unsupported until a reliable discovery/validation interface is available. Runtime
configuration is inherited for empty overrides; availability still needs runtime
verification. Changed project choices require explicit reconfiguration; skill
conflicts always require manual review and are never forced by that flag.

`doctor` is a read-only report, not campaign state or an infrastructure manager.
General checks need no CUDA. Workload checks require declared prior target approval
and explicit relevant requirements. Fixed isolated framework probes use the trusted
workload interpreter; artifact identities are streamed locally. Requirements beyond
lightweight discovery remain NOT CHECKED and require approved workload probes.
No automatic dependency repair, downloads, model loading or application execution.

Approval UI belongs to the active agent/mode. The skill checks actual tool
availability, using structured choices only when usable and conversational choices
otherwise. Approve authorizes only the exact proposal; changes require revision and
fresh approval; decline preserves evidence. Tool errors/defaults are not consent.

Forge and artifact schemas remain unchanged. The ledger remains authoritative for
targets/lineage. No database or guessed conversational status is added.
