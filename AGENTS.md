# Development

Follow TDD: write a meaningful test, observe the expected behavioral failure,
implement the smallest change, rerun it and relevant existing tests.
For behavior-preserving refactoring, establish a passing baseline first.

Run `./test.sh`. Bridge-only changes also require `bash bridge/scripts/test.sh`
on an Apple-silicon Mac. Avoid real-device tests and setup against someone else's
runtime; use temporary directories and mocks. Never commit credentials, IPAs,
provisioning profiles, pairing records, runtime state, or machine-specific paths.
Never uninstall apps or revoke signing certificates as a repair strategy.
