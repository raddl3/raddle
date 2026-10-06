# Accepted artifact handoff

Read the [public integration guide](https://github.com/raddl3/raddle/blob/main/docs/guides/external-workload.md)
and [artifact API](https://github.com/raddl3/raddle/blob/main/src/raddle/artifact.py).
The complete external example includes wheel construction and readback.

1. Inspect campaign acceptance; obtain `incumbent_source()` and preserve the ledger
   containing the approved target/hash. Keep it alongside the artifact; the existing
   artifact schema does not carry the Forge target or authenticate approval.
2. Build the workload wheel from that snapshot. Verify its source member bytes
   against the incumbent hash. Build a Raddle wheel matching the running package.
3. Call `create_external_artifact` with descriptor/case, reference and candidate
   callables, a `ValidationReceipt` callback, canonical inputs, full reference Git
   revision/URL, invocations, validation method, profile, dependency versions,
   wheel/package/source-member identities, lockfile, timing parameters and commands.
4. Call `read_artifact` and compare the manifest candidate hash with the incumbent.

Packaging revalidates before timing and measures a separate run. Report Forge
selection and artifact timings separately. Readback checks integrity, not execution;
ensure the packaged bytes are the candidate that ran. Keep every failed result out
of accepted artifacts and require review before adoption.

5. Call `campaign.record_artifact(output)` to bind the verified manifest hash to
   the accepted winner. After approved adoption, apply and verify, then offer the
   next loop and STOP. Keep the trusted reference unchanged in later artifacts.
