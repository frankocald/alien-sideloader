#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Apollo Sideload contributors.
"""Refresh only Apollo's cached profiles; publish a validated complete set."""
import argparse, datetime as dt, hashlib, json, os, pathlib, shutil, subprocess, tempfile

TARGETS = ['Apollo', 'ApolloIntentions', 'ApolloRebornWidgets', 'Apollofari',
           'ApollofariLegacy', 'NotificationContentExtension', 'NotificationServiceExtension', 'OpenInUIExtension']
from identity import load

def decode(path):
    import plistlib
    return plistlib.loads(subprocess.check_output(['/usr/bin/security','cms','-D','-i',str(path)], stderr=subprocess.DEVNULL))

def expected(base, name, team):
    project = json.loads((base/'ApolloSigning'/name/'Signing.xcodeproj/project.pbxproj').read_text())
    ids = {o.get('buildSettings', {}).get('PRODUCT_BUNDLE_IDENTIFIER') for o in project['objects'].values()}
    ids.discard(None)
    if len(ids) != 1: raise RuntimeError('Ambiguous bundle ID for '+name)
    return team+'.'+ids.pop()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--config',type=pathlib.Path,required=True)
    ap.add_argument('--base', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parent)
    ap.add_argument('--min-hours', type=float, default=144)
    a=ap.parse_args();identity=load(a.config)
    CERT=identity['certificate'];TEAM=identity['team'];DEVICE=identity['udid']
    base=a.base.resolve();dest=base/'apollo-signing-profiles'
    import fcntl
    lock=open(base/'.renew-profiles.lock','a');fcntl.flock(lock,fcntl.LOCK_EX)
    old={n:decode(dest/(n+'.mobileprovision')) if (dest/(n+'.mobileprovision')).exists() else None for n in TARGETS}
    ids={n:expected(base,n,TEAM) for n in TARGETS}
    caches=[pathlib.Path.home()/'Library/Developer/Xcode/UserData/Provisioning Profiles',
            pathlib.Path.home()/'Library/MobileDevice/Provisioning Profiles']
    with tempfile.TemporaryDirectory(prefix='.renew-',dir=base) as tmp:
        root=pathlib.Path(tmp);stage=root/'profiles';stage.mkdir();backups=[];committed=False
        try:
            for cache in caches:
                for p in cache.glob('*.mobileprovision'):
                    try: profile=decode(p)
                    except Exception: continue
                    if profile.get('Entitlements',{}).get('application-identifier') in ids.values():
                        backup=root/('backup-'+str(len(backups)));shutil.copy2(p,backup)
                        backups.append((p,backup));p.unlink()
            rows=[]
            for name in TARGETS:
                products=root/name/'products'
                command=['/usr/bin/xcodebuild','-project',str(base/'ApolloSigning'/name/'Signing.xcodeproj'),
                         '-target',name,'-configuration','Debug','-destination','generic/platform=iOS',
                         '-allowProvisioningUpdates','SYMROOT='+str(products),'OBJROOT='+str(root/name/'objects'),'build']
                subprocess.run(command,check=True,timeout=180)
                suffix='app' if name=='Apollo' else 'appex'
                p=products/'Debug-iphoneos'/(name+'.'+suffix)/'embedded.mobileprovision';d=decode(p)
                now=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
                ent=d.get('Entitlements',{})
                if ent.get('application-identifier')!=ids[name] or DEVICE not in d.get('ProvisionedDevices',[]):
                    raise RuntimeError('Wrong bundle/device in '+name)
                if old[name] and d['ExpirationDate']<=old[name]['ExpirationDate']:
                    raise RuntimeError('Xcode reused the expiration for '+name)
                if d['ExpirationDate']<now+dt.timedelta(hours=a.min_hours):
                    raise RuntimeError('Insufficient new profile validity for '+name)
                if CERT.lower() not in [hashlib.sha1(c).hexdigest() for c in d['DeveloperCertificates']]:
                    raise RuntimeError('Wrong signing certificate for '+name)
                if set(ent.get('com.apple.security.application-groups',[])) != ({identity['group']} if name in __import__('identity').GROUP_TARGETS else set()):
                    raise RuntimeError('Shared app group changed for '+name)
                shutil.copy2(p,stage/(name+'.mobileprovision'))
                rows.append({'target':name,'uuid':d['UUID'],'expires':d['ExpirationDate'].isoformat()+'Z'})
            dest.mkdir(exist_ok=True)
            previous=root/'previous';os.rename(dest,previous)
            try: os.rename(stage,dest)
            except BaseException: os.rename(previous,dest);raise
            committed=True
            print('RENEWED_PROFILES='+json.dumps(rows),flush=True)
        finally:
            if not committed:
                for p,backup in backups:
                    p.parent.mkdir(parents=True,exist_ok=True)
                    if not p.exists():shutil.copy2(backup,p)

if __name__=='__main__':main()
