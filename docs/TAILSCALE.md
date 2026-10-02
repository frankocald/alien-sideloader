# Optional remote bridge

The simple wizard path uses Apple's local network CoreDevice connection. Remote
installation is optional and has a separate Apple trust relationship. Tailscale
alone does not open the phone's Apple RemotePairing listener.

Requirements:

- Apple-silicon Mac, full Xcode, Tailscale on both devices in the same tailnet.
- Developer Mode, an already trusted phone, and an owner-only RemotePairing record
  containing the **verified phone signing identity**.
- Wi-Fi on the phone during first acquisition/reacquisition. The Wi-Fi need not be
  the Mac's LAN. Enable Tailscale and wait for `active` before changing networks.

During wizard setup choose the optional bridge. You can either import an existing
verified record or create a new one through trusted USB. New pairing requires
**Python 3.12** for the optional pinned `pymobiledevice3` helper. Install it before
starting remote setup if necessary:

```sh
brew install python@3.12
```

If it is not on PATH, give the wizard the path printed by Homebrew. The wizard
creates an isolated virtual environment in the private runtime and installs
`pymobiledevice3==11.12.4` and `cryptography==50.0.2`. No global Python packages are
changed. These optional downloaded dependencies are additional code you trust;
transitive Python dependencies are not hash-locked. The helper uses the already
trusted **USB** session and verifies the accessory's Ed25519 signature before
saving its public key. It reuses an existing runtime host identity on retries;
it never resets normal Xcode trust or disables phone signature verification.

Keep the intended phone unlocked and USB connected for that step. Missing USB
trust, an unexpected helper API, or an invalid phone signature stops setup. A
partial seed record is not treated as a pinned record. The dynamic helper adapts
only the expected pinned upstream method and fails if its source shape changes.
New-device USB pairing still needs end-to-end verification on additional devices;
see VERIFICATION.md. You can skip the remote option and use LAN mode.

For importing a record, the wizard rejects wrong-device, unpinned and publicly
readable files. Never invent a pin, capture it from an unauthenticated network
response, share another person's record, or remove verification to make setup
succeed. Normal Xcode pairing is separate from this RemotePairing record.

The wizard builds the included hardened bridge from verified/pinned source, stores
the record privately, checks the configuration and installs its separate
LaunchAgent. The record and bridge configuration are not public source files.

After setup, status:

```sh
runtime="$HOME/Library/Application Support/ApolloSideload"
"$runtime/assets/tailscale-bridge/ios-ota" status --profile "$runtime/bridge/iphone.json"
```

Loss of the Apple tunnel on pure cellular requires joining Wi-Fi to reconnect.
Turning Tailscale off can end that tunnel. No perpetual cellular connection or
locked-phone guarantee is offered. Do not expose the local forwarding port on
public interfaces or enable Tailscale Funnel. Review `bridge/README.md` for source
architecture and CLI options; its upstream examples are not your runtime paths.
