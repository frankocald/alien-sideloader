# Attribution and licensing

Copyright (c) 2026 Apollo Sideload contributors.

This project's original automation, wizard, and USB pairing helpers are licensed
under **GPL-3.0-only**. The complete license is in `LICENSE` and
`licenses/GPL-3.0.txt`. When distributing the program or modified versions,
comply with GPLv3, including its corresponding-source and license requirements.
Private modifications do not require publication merely because they are made.

Included upstream bridge code retains its original MIT license and notices in
`bridge/LICENSE` and `bridge/THIRD_PARTY_NOTICES.md`. Preserve these notices when
redistributing it. The optional USB pairing program adapts a GPL-licensed upstream
method at runtime and runs as a separate process.

This license grants no rights to Apollo, Apollo Reborn, Apple software, or other
third-party applications beyond their own licenses.

- **iOS OTA**, by zjz-connect / lyo-eos:
  https://github.com/lyo-eos/ios-ota. The `bridge/` directory is a modified source
  snapshot based on commit `d50141ad7af63acf74f92f967f17e942488c666b`. Its original copyright and MIT license are preserved in
  `bridge/LICENSE`. Changes add authenticated local forwarding, pinned device
  verification, bounded handshake deadlines, and a verified toolchain/build
  process. There is no cellular RPC heartbeat in this copy.
- **go-ios**, by Daniel Paulus and contributors:
  https://github.com/danielpaulus/go-ios. The bridge fetches pinned commit
  `3ebc297691a9e364772aef027744ebc0c49421a5` and applies a source patch.
  The MIT notice is preserved in `bridge/THIRD_PARTY_NOTICES.md`.
- **Apollo Reborn**, by its contributors:
  https://github.com/Apollo-Reborn/Apollo-Reborn. This project downloads the
  user's chosen official stable GLASS IPA; no IPA, tweak binary, app resources,
  or Apollo Reborn source is included. The upstream repository states GPL-3.0:
  https://github.com/Apollo-Reborn/Apollo-Reborn/blob/main/LICENSE. Refer to its
  source and license for that component; the underlying Apollo app is separate.
- **Apollo**, by Christian Selig: https://apolloapp.io/. Names are used to identify
  the app; this project is not endorsed by or affiliated with its author.
- **guide-sideloading-ios-mac**, by teebow1e:
  https://github.com/teebow1e/guide-sideloading-ios-mac, provided the conceptual
  starting point for the Xcode signing workflow. No source from that repository
  is included here.
- **pymobiledevice3**, by doronz88 and contributors:
  https://github.com/doronz88/pymobiledevice3. Optional USB pairing uses pinned
  version 11.12.4 and adapts its expected RemotePairing method to retain a private
  host identity and verify the phone signature. It is downloaded separately into
  a private virtual environment and is GPL-3.0 licensed:
  https://github.com/doronz88/pymobiledevice3/blob/master/LICENSE. Its complete
  license is included in `licenses/GPL-3.0.txt`; upstream source is available at
  that repository. The adapted method is generated from that source at runtime.
- **cryptography**, by the Python Cryptographic Authority:
  https://github.com/pyca/cryptography. Optional pinned dependency (50.0.2), not
  bundled; its license is https://github.com/pyca/cryptography/blob/main/LICENSE.
- **Tailscale**, Apple Xcode/CoreDevice, and Discord are external dependencies or
  optional services, not redistributed here. Their own terms and licenses apply.

Exact iOS OTA base commit: `d50141ad7af63acf74f92f967f17e942488c666b`.
Only source is distributed. Before distributing compiled bridge binaries, include
all applicable notices for Go and the transitive modules listed in `bridge/go.mod`.
