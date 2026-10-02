# Apollo Sideload

A macOS setup wizard and deterministic background job for signing Apollo Reborn,
retaining all seven extensions, and installing over the same app identity. Local
network installation comes first; an optional hardened Tailscale bridge provides
remote installation. Optional Discord notifications support emoji reaction retries.
No LLM, OpenClaw, server subscription, or administrator Discord access is required.

## Quick start

1. Install full Xcode, open it once, accept its license, and add your Apple Account
   in **Xcode → Settings → Accounts**. Under **Manage Certificates**, create an
   **Apple Development** certificate if you do not already have one. The wizard
   reuses a certificate; it does not create or revoke certificates.
2. Connect your unlocked iPhone by USB, trust the Mac, enable **Developer Mode**
   under **Settings → Privacy & Security**, and complete Xcode's device preparation.
   Enable wireless connectivity in Xcode's Devices and Simulators window if that
   option is shown. Confirm the phone appears in `xcrun devicectl list devices`.
3. Download/clone this source repository. Open Terminal in its folder and run:

   ```sh
   bash setup.command
   ```

   A downloaded ZIP may require right-click → Open for `setup.command`; running
   it from Terminal is sufficient. No `sudo` is needed. macOS's Xcode-provided
   `/usr/bin/python3` runs the worker; no Python packages are required for LAN mode.
4. Choose the phone and development certificate, confirm your ten-character Team
   ID, and enter a unique reverse-domain bundle ID such as `org.yourname.Apollo`.
   Accept the generated shared-group default **for a new installation only**.
   Discord and Tailscale can both be skipped. Optional remote setup can create a
   verified pairing record through trusted USB; it additionally needs Python 3.12.
5. The wizard downloads the latest stable **GLASS IPA with extensions**, generates
   eight small provisioning projects, and asks Xcode for matching profiles. Allow
   any Xcode/Keychain prompts. It never installs the placeholder projects.
6. Choose whether to enable the schedule. Enabling it authorizes signing and
   installation and starts the first attempt immediately. Otherwise, the wizard
   prints the manual command. Keep the iPhone on the Mac's Wi-Fi for the first LAN
   installation, then check the worker log to confirm success.

The wizard never asks for your Apple Account password. Xcode/Keychain handles
Apple authentication. Personal values and optional Discord credentials are stored
outside the source tree in a private runtime directory.

### Existing Apollo installations: preserve the identity

Export a backup from Apollo before changing installers. Reuse the existing signed
app's **exact bundle ID, Team ID, shared app group, certificate, and keychain
identity**. The wizard cannot reliably infer all of these from an installed app.
If you do not know them, stop and consult the signing configuration that created
that installation. A newly generated group is not a migration of an old group.

The signer changes only the original upstream Apollo bundle prefix to the
configured prefix and checks all eight identities. It never uninstalls Apollo.
An in-place installation retains its app-container identity, but this does not
protect against upstream app bugs, incompatible data migrations, or iOS failures.
Changing Team ID/certificate can affect keychain access. Make a backup.

## Runtime and daily use

Default runtime: `~/Library/Application Support/ApolloSideload/`. It contains
scripts, generated projects, signing profiles, original/prepared IPAs, state,
bounded logs, and optional credentials/pairing material. Source code is portable;
runtime contents are private and must never be published.

The wizard refuses to overwrite an existing runtime. To complete interrupted
setup, run `bash setup.command --resume`. To create a separate installation, use
`bash setup.command --root "/absolute/path/to/private/runtime"`. Do not schedule
multiple workers for the same phone/app; only one public worker LaunchAgent label
is supported per macOS login.

```sh
# Status (private device/signing information can appear)
/usr/bin/python3 "$HOME/Library/Application Support/ApolloSideload/assets/apollo-sideload-job.py" --status

# Request an immediate run, respecting retry limits
/usr/bin/python3 "$HOME/Library/Application Support/ApolloSideload/assets/apollo-sideload-job.py" --run-now

# Stop the schedule; retain the app and private runtime
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/io.github.apollo-sideload.worker.plist"
```

With a custom runtime, add `--root "/absolute/path/to/private/runtime"` to worker
commands. Inspect `logs/worker.log`, `renew.log`, `sign.log`, `local-install.log`
and `tailscale-install.log` inside the runtime. Do not post logs without reviewing
and redacting personal paths/device IDs. There is no automatic uninstall command.

The LaunchAgent checks every ten seconds while the Mac is awake and logged in.
A cycle begins six days after the last successful installation, or one day before
the earliest installed profile expires, whichever comes first. Sleep or outages
can cause renewal to miss its deadline. First unlock after a phone reboot may be
required; unattended locked-phone behavior is not guaranteed.

Every attempt checks GitHub's latest stable release, including reaction/manual
retries. It skips prereleases, older versions, other variants, and assets without
GitHub SHA-256 digests. Download limits, ZIP validation and exact app/extension
identity checks apply before replacing the original IPA. A failed check retains
the current IPA so signing can continue. A verified new IPA invalidates the
prepared retry cache. Version comparison uses the Reborn asset version, not the
underlying original Apollo version. Same-version asset replacements are skipped.

All eight profiles are checked for the same team/device/certificate and app-group
assignments, with at least six days of validity required. On renewal, expiration
must advance for every existing exported profile. Only this app's matching cached
profiles are temporarily removed; failed renewal restores backups. This workflow
was designed for seven-day development signing. Paid-team renewal behavior and
all account/capability combinations are not established. Apple imposes app/App-ID
and capability limits; the eight identities here may use most of a free account's
weekly quota. The wizard cannot bypass Apple restrictions.

There are three automatic attempts per cycle with increasing delays. A persistent
lock and state prevent overlap and preserve retry limits across restarts. At most
eight attempts are allowed per rolling day. Automatic and CLI retries also have
an hourly limit; Discord reactions bypass that hourly limit. `--fresh-run` is an
explicit debugging override, not a scheduled operation. Without Discord, inspect
logs and use `--run-now` after restoring connectivity; the automatic retries still
work. See [Discord setup](docs/DISCORD.md) and [Tailscale setup](docs/TAILSCALE.md).

## Trust, security and limitations

- This is unofficial software, not endorsed by Apple, Apollo's author, Apollo
  Reborn, Tailscale, or Discord. It is provided without warranty under the GPLv3
  license (GPL-3.0-only for this project’s original code; see notices). You are responsible for complying with applicable software licenses,
  service terms, and account rules. This repository grants no rights to app IPAs.
- Automatic updates trust **future upstream release executable code**. A matching
  checksum verifies transfer integrity against GitHub's metadata; it is not a
  malware audit or an independent signature of the publisher. Review releases
  and disable the job if you no longer trust the upstream project.
- Signing keys remain in macOS Keychain. The worker requires access to that key
  while logged in. Restrict your Mac account and avoid sharing that signing key.
- Discord tokens and Apple pairing records are credentials. Keep the runtime
  owner-only and never commit it or share it in support tickets. A pairing record
  can grant significant access to the phone; revoke its trust on the phone if it
  leaks. Use a dedicated Discord bot with permissions in one channel only.
- The bridge verifies the pinned phone identity and authenticates the local
  forwarding port. No public port-forward, relay server or Tailscale Funnel is
  configured. Tailscale access controls and the integrity of your Mac still matter.
- Fresh cellular-only connection after losing the Apple tunnel is unsupported.
  Join **any Wi-Fi network**, enable Tailscale and wait for bridge `active` to
  reacquire it. Keeping Tailscale off is compatible with LAN installs, but remote
  installation needs it enabled. No cellular keepalive workaround is included.
- Failure notifications require a reachable Discord service. Queues are persistent
  but delivery is not instant during outages, and rare crash-window duplicates
  are possible. Expired development profiles can stop the app opening.

## Development and publication

Run `./test.sh` (Python tests use mocks/temp directories and require no device).
On Apple-silicon macOS, run `bash bridge/scripts/test.sh` for the pinned Go bridge
package tests, race checks and vet. The bridge build downloads a checksum-verified
Go toolchain and pinned go-ios source; it does not alter global Go installations.
Follow [AGENTS.md](AGENTS.md), including TDD.

The source snapshot contains no IPAs, certificates, private keys, provisioning
profiles, pairing records, runtime configuration or existing Git history. Avoid
adding those files; `.gitignore` is defense in depth, not a secret scanner. Review
`git diff --cached` and the complete tracked file list before publishing. Do not
copy your runtime into this repository. See [verification](docs/VERIFICATION.md)
for the exact validation completed and its limits, and
[third-party notices](THIRD_PARTY_NOTICES.md) for credits and licensing.
