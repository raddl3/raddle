Use the Raddle acceleration skill in this repository.

Profile the existing project and identify one measured repetitive numerical bottleneck. Preserve the reference implementation and existing correctness tests.

If a compatible Raddle accelerator exists, integrate it using the smallest safe change. Validate against the reference and benchmark the same representative workload before and after. Keep the integration only if validation passes and the measured result is worthwhile.

If no accelerator matches, return a Raddle Forge candidate report instead of inventing one.

Return the exact workload, baseline timing, accelerated timing, speedup, validation result, provenance, changed files, and reproduction commands.
