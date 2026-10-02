# Existing GPU over SSH: workflow and proposed executor

Status: design only. Raddle currently has no SSH executor or generic project
execution command. Existing workload commands can already be run manually on
user-controlled GPU compute. This does not require uploading code to Raddle.
Forge architecture, validation gates, benchmark receipts, and artifact schemas
remain unchanged.

## User-managed workflow today

Keep development in a local isolated candidate worktree. Use a GPU host alias
from your own SSH configuration, keys, or agent. Preserve normal host-key
checking. No keys, tokens, host aliases, or credentials belong in shared results.

1. Review the plan and agree on the candidate revision, required inputs, target
   hardware, reference/validation commands, benchmark boundary, and result paths.
2. Create a fresh remote directory under a user-owned location. Transfer only
   reviewed source and required inputs with `rsync` or `scp`. A worktree's `.git`
   file points to the local repository and cannot be reused remotely. Exclude
   `.git`, virtual environments, caches, `.env` files, credentials, and unrelated
   data; prefer an explicit file allowlist. Do not use `rsync --delete` against
   an existing project. Check staged source and input hashes against local bytes.
3. Run the project's locked setup and existing workload commands through `ssh`
   from that directory. Use the same pinned dependencies and candidate bytes.
   Collect the workload's allowlisted environment/provenance (OS, Python,
   dependencies, GPU model/driver/runtime, source and input identities), rather
   than dumping environment variables or host identity.
4. Execute the existing Forge evaluation command remotely. Forge must validate
   before benchmarking; do not implement that ordering in a second remote gate.
   If validation fails, retrieve the failure record without a speedup claim.
5. Retrieve the structured ledger/receipts and accepted artifact, keeping raw
   stdout/stderr as local diagnostics. Check exit status, JSON parsing, source
   identities, receipt validation status, and artifact hashes/readback before
   accepting results. Remote timings describe that host and stated workload,
   not the local machine. Retain remote files for inspection until the user
   chooses cleanup.

Illustrative transport commands, after configuring `my-gpu` and creating a
fresh remote directory (replace paths and project-specific command):

```sh
ssh my-gpu 'mkdir -p /tmp/my-reviewed-candidate'
rsync -av --files-from=reviewed-files.txt ../project-raddle-candidate/ my-gpu:/tmp/my-reviewed-candidate/
ssh my-gpu 'cd /tmp/my-reviewed-candidate && task evaluate'
scp -r my-gpu:/tmp/my-reviewed-candidate/results ./remote-results
```

`reviewed-files.txt`, `task evaluate`, and `results` are project-specific, not
Raddle APIs. The file list must include the required lockfile and inputs while
excluding private files. A project with an existing remote checkout may instead
stage the agreed revision plus reviewed changes there in a separate directory.
Do not reuse old result files as a successful new run.

## Smallest proposed implementation

Use OpenSSH and `rsync`/`scp` as subprocesses, not an SSH library or provider
framework. A public, opt-in transport helper would take a user-managed SSH host
alias, a fresh remote directory, an explicit staging allowlist, a trusted
project command, and declared structured-result paths. It would:

- stage the isolated candidate when needed and verify content identities;
- execute the command with quoted remote arguments, a timeout, and checked exit
  status; keep diagnostics separate from structured results;
- retrieve workload-produced environment/provenance and validation/benchmark
  records, rejecting missing, stale, malformed, or mismatched results;
- leave numerical validation, benchmarking, acceptance, and artifact packaging
  to the existing workload adapter and Forge.

Do not embed host aliases or private remote paths in portable evidence. Do not
store authentication, forward an SSH agent by default, bypass host-key checking,
provision machines, schedule jobs, or add managed Run/billing/provider interfaces.

## Why implementation stops here

The public package has no arbitrary-project command/result contract: Forge
accepts in-process build, validate, and benchmark callbacks, and individual
workloads own their commands, ledgers, and packaging. Automatic synchronization
also needs an agreed file/data allowlist and a reliable way to bind retrieved
results to the staged candidate. That is a new execution contract, not a small
addition to `agent init`.

Before implementing, demonstrate one concrete workload adapter with declared
setup/evaluation commands, input files, result paths, provenance, and failure
behavior. Then add only its SSH transport and a runnable local/fake-SSH check
covering command failure, validation rejection, and retrieval identity. No
executor hierarchy is needed. The platform remains a presentation consumer;
public execution must work without hosted services.
