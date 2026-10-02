# Verification and remaining limits

Verified on macOS with Xcode 26.6, 2026-10-02:

- TDD contract tests first failed because the copied worker still used personal
  values, setup did not create private runtime/projects/LaunchAgent, and disabling
  Discord left an undeliverable queue. These assertions passed after implementation.
- Optional bridge tests first failed because unpinned/wrong-device records were not
  rejected/imported and the wizard did not run the USB pairing bootstrap. They
  passed after implementation.
- Cryptographic tests first failed because bootstrap did not produce an independent
  matching host keypair or verify the phone signature. They now verify fresh key
  generation, successful authenticated pinning, and rejection of a changed identity.
- Resume tests first failed because an already complete profile set was not reused.
  The wizard now reuses only a complete, valid matching eight-profile set.
- 37 core Python tests pass. They cover update version selection, checksum rejection,
  missing extensions, download failure fallback, retry-cache invalidation, existing
  worker retry/state behavior, config identity, optional Discord, setup isolation,
  credentials permissions, project generation, pairing record import and resume.
- Two optional cryptographic tests pass with Python 3.12 and cryptography 50.0.2.
  Run these with `python3.12 -m unittest discover -s tests_optional` in an environment
  containing cryptography. Core tests run using `/usr/bin/python3` with no packages.
- The expected four adapter strings each match exactly once in pymobiledevice3
  11.12.4's USB pairing implementation; unexpected source shape fails closed.
- The included bridge's selected nine dependency package suites and complete bridge
  unit suite, race suite and vet passed using its pinned verified build process.
- Generated main-app and app-extension provisioning projects built successfully for
  generic iOS devices with `CODE_SIGNING_ALLOWED=NO`. These builds install nothing
  and contact no provisioning service. Real signing/account compatibility remains
  unverified for the new wizard.

The original private installation demonstrated hardened bridge installations over
Wi-Fi and an already-open tunnel on cellular. Those historical results do not
constitute an end-to-end test of a fresh user's wizard or Apple account.

No public-wizard setup was run against a live Apple account or phone. It would
create profiles/trust and could affect an existing installation. Fresh USB pairing,
new-user Xcode provisioning, scheduled first installation and Discord bot permissions
need validation on a separate test account/device. The setup code is ready for that
test, but should be described as experimental until it passes.

The helper depends on a pinned upstream private API; macOS/iOS/Xcode updates can
break it. Seven-day signing with preserved extensions may encounter Apple account
limits. Paid-team behavior, first-unlock-after-reboot, long-idle locked-phone
operation, and new-device cellular-only acquisition are not promised.

Only source is packaged. No IPA, real device identity, signing profile, pairing
record, Discord token, private key, compiled bridge, machine log or original Git
history is included. Synthetic identities and cryptographic keys in automated
tests are fixtures. Review your own staged files/history before publication; future
local setup output must remain outside the repository.
