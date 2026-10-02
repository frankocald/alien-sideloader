#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Apollo Sideload contributors.
"""Resign Apollo and each preserved extension with its own Xcode profile."""
import argparse, datetime, plistlib, shutil, subprocess, tempfile, zipfile
from pathlib import Path

from identity import load, OLD_ID, OLD_GROUP


def run(*args, capture=False):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE if capture else None).stdout


def read_profile(path):
    return plistlib.loads(run('security', 'cms', '-D', '-i', str(path), capture=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('ipa', type=Path)
    parser.add_argument('--profiles', type=Path, default=Path(__file__).resolve().parent/'apollo-signing-profiles')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--install', action='store_true')
    parser.add_argument('--device')
    parser.add_argument('--transport', choices=['devicectl', 'tailscale'], default='devicectl')
    args = parser.parse_args()
    identity=load(args.config)
    CERT=identity['certificate'];NEW_ID=identity['bundle_id'];NEW_GROUP=identity['group']
    if args.install and args.transport == 'devicectl' and not args.device:
        parser.error('--install requires --device')
    if args.output.resolve() == args.ipa.resolve():
        parser.error('output must differ from the original IPA')
    if len(OLD_GROUP.encode()) != len(NEW_GROUP.encode()):
        raise RuntimeError('Group replacements must preserve binary string length')
    with tempfile.TemporaryDirectory(prefix='apollo-resign-') as directory:
        root = Path(directory)
        with zipfile.ZipFile(args.ipa) as z:
            for member in z.infolist():
                path = (root/member.filename).resolve()
                if not path.is_relative_to(root.resolve()):
                    raise RuntimeError('Unsafe ZIP entry')
            # ditto preserves Unix modes/symlinks in iOS app bundles.
        run('ditto', '-x', '-k', str(args.ipa.resolve()), str(root))
        apps = list((root/'Payload').glob('*.app'))
        if len(apps) != 1:
            raise RuntimeError('Expected exactly one main app')
        app = apps[0]
        bundles = [app, *sorted(app.glob('PlugIns/*.appex'))]
        certificates = run('security','find-identity','-v','-p','codesigning',capture=True).decode()
        if CERT not in certificates:
            raise RuntimeError('Configured signing identity is unavailable')
        decoded = {}
        for bundle in bundles:
            profile_path = args.profiles/(bundle.stem+'.mobileprovision')
            profile = read_profile(profile_path)
            if profile['ExpirationDate'] <= datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None):
                raise RuntimeError(f'Expired profile: {bundle.stem}')
            import hashlib
            if CERT.lower() not in [hashlib.sha1(c).hexdigest() for c in profile['DeveloperCertificates']]:
                raise RuntimeError(f'Profile does not contain signing certificate: {bundle.stem}')
            info_path = bundle/'Info.plist'
            info = plistlib.loads(info_path.read_bytes())
            old = info['CFBundleIdentifier']
            if not (old == OLD_ID or old.startswith(OLD_ID+'.')):
                raise RuntimeError(f'Unexpected bundle ID: {old}')
            new = NEW_ID + old[len(OLD_ID):]
            identifier = profile['Entitlements']['application-identifier']
            if identifier.split('.',1)[1] != new:
                raise RuntimeError(f'Profile bundle ID mismatch for {bundle.stem}')
            info['CFBundleIdentifier'] = new
            info_path.write_bytes(plistlib.dumps(info, fmt=plistlib.FMT_BINARY))
            shutil.copy2(profile_path, bundle/'embedded.mobileprovision')
            ent = dict(profile['Entitlements'])
            # Expand profile wildcard keychain access to the shared main-app group.
            if 'keychain-access-groups' in ent:
                prefix = identifier.split('.',1)[0]
                ent['keychain-access-groups'] = [prefix+'.'+NEW_ID]
            entitlement_file = root/(bundle.stem+'.entitlements')
            entitlement_file.write_bytes(plistlib.dumps(ent))
            decoded[bundle] = entitlement_file
        # Update equal-length shared-container literals without moving Mach-O offsets.
        for file in app.rglob('*'):
            if not file.is_file() or file.is_symlink() or file.name == 'embedded.mobileprovision' or '_CodeSignature' in file.parts:
                continue
            content = file.read_bytes()
            if OLD_GROUP.encode() in content:
                file.write_bytes(content.replace(OLD_GROUP.encode(),NEW_GROUP.encode()))
                print('Updated shared group:',file.relative_to(app),flush=True)
        def sign(path, ent=None):
            cmd=['codesign','--force','--sign',CERT,'--timestamp=none','--generate-entitlement-der']
            if ent:cmd += ['--entitlements',str(ent)]
            run(*cmd,str(path))
        # Sign inside out; never reuse the main app's profile on extensions.
        nested=[p for p in app.rglob('*') if p.suffix in ('.dylib','.so','.framework','.bundle')]
        for path in sorted(nested,key=lambda p:len(p.parts),reverse=True):
            if path.suffix=='.bundle':
                info=path/'Info.plist'
                if not info.exists() or not plistlib.loads(info.read_bytes()).get('CFBundleExecutable'):
                    continue
            sign(path)
        for bundle in bundles[1:]:
            sign(bundle,decoded[bundle])
            run('codesign','--verify','--deep','--strict',str(bundle))
        sign(app,decoded[app])
        run('codesign','--verify','--deep','--strict',str(app))
        args.output.parent.mkdir(parents=True,exist_ok=True)
        temp_output=root/'signed.ipa'
        run('ditto','-c','-k','--keepParent',str(root/'Payload'),str(temp_output))
        shutil.copy2(temp_output,args.output)
        print('Verified IPA saved:',args.output,flush=True)
        if args.install:
            if args.transport == 'tailscale':
                raise RuntimeError('Use the worker for optional Tailscale installation')
            else:
                run('xcrun','devicectl','device','install','app','--device',args.device,'--timeout','60',str(app))


if __name__ == '__main__':
    main()
