# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Apollo Sideload contributors.
"""Fetch newer stable Apollo Reborn GLASS releases without changing bundle identity."""
import hashlib, json, logging, os, pathlib, plistlib, re, stat, tempfile, time, urllib.request, zipfile

API='https://api.github.com/repos/Apollo-Reborn/Apollo-Reborn/releases/latest'
PATTERN=re.compile(r'Apollo-Reborn-(\d+\.\d+\.\d+)-GLASS\.ipa')
EXPECTED={'Apollo':'com.christianselig.Apollo','ApolloIntentions':'com.christianselig.Apollo.ApolloIntentions',
'ApolloRebornWidgets':'com.christianselig.Apollo.RebornWidgets','Apollofari':'com.christianselig.Apollo.Apollofari',
'ApollofariLegacy':'com.christianselig.Apollo.ApollofariLegacy',
'NotificationContentExtension':'com.christianselig.Apollo.NotificationContentExtension',
'NotificationServiceExtension':'com.christianselig.Apollo.NotificationServiceExtension',
'OpenInUIExtension':'com.christianselig.Apollo.OpenInUIExtension'}

def version(value):
    if not re.fullmatch(r'\d+\.\d+\.\d+',value):raise ValueError('Invalid release version')
    return tuple(map(int,value.split('.')))

def validate(path):
    found={}
    with zipfile.ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist())>1024**3:raise ValueError('Oversized IPA')
        for i in z.infolist():
            name=i.filename;p=pathlib.PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name:raise ValueError('Unsafe IPA path')
            if stat.S_ISLNK(i.external_attr>>16):raise ValueError('Unexpected IPA symlink')
            if name.startswith('Payload/') and name.endswith('/Info.plist') and (name.count('/')==2 or (name.count('/')==4 and '/PlugIns/' in name)):
                key=p.parent.stem
                if key in found:raise ValueError('Duplicate bundle')
                found[key]=plistlib.loads(z.read(i))['CFBundleIdentifier']
        if found!=EXPECTED:raise ValueError('App or extension identities changed')
        if z.testzip() is not None:raise ValueError('Corrupt IPA')

def request(url):
    return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'ApolloSideload/1.0','Accept':'application/vnd.github+json'}),timeout=20)

def update(root):
    """Return True only when original.ipa changed. Failures retain the existing IPA."""
    root=pathlib.Path(root);target=root/'original.ipa';metadata=root/'release.json';temporary=None;replaced=False
    try:
        local=json.loads(metadata.read_text());current=version(local['version'])
        with request(API) as response:release=json.loads(response.read(2*1024*1024))
        if release.get('draft') or release.get('prerelease'):raise ValueError('Not a stable release')
        assets=[a for a in release['assets'] if PATTERN.fullmatch(a['name'])]
        if len(assets)!=1:raise ValueError('Expected one GLASS IPA with extensions')
        asset=assets[0];candidate=PATTERN.fullmatch(asset['name']).group(1)
        if version(candidate)<=current:return False
        url=asset['browser_download_url']
        prefix='https://github.com/Apollo-Reborn/Apollo-Reborn/releases/download/'
        if not url.startswith(prefix):raise ValueError('Unexpected release download URL')
        digest=asset.get('digest','')
        if not re.fullmatch(r'sha256:[a-f0-9]{64}',digest):raise ValueError('Missing SHA-256 release digest')
        size=asset['size']
        if not 0<size<=250*1024**2:raise ValueError('Invalid release size')
        fd,temporary=tempfile.mkstemp(prefix='.release-',suffix='.ipa',dir=root)
        sha=hashlib.sha256();received=0;deadline=time.monotonic()+180
        with os.fdopen(fd,'wb') as out,request(url) as response:
            while True:
                if time.monotonic()>deadline:raise TimeoutError('Release download time limit')
                block=response.read(1024**2)
                if not block:break
                received+=len(block)
                if received>size:raise ValueError('Release exceeds expected size')
                sha.update(block);out.write(block)
            out.flush();os.fsync(out.fileno())
        if received!=size or sha.hexdigest()!=digest.split(':')[1]:raise ValueError('Release checksum or size mismatch')
        validate(temporary)
        # A crash after IPA replacement leaves older metadata: next run safely downloads again.
        os.replace(temporary,target);temporary=None;replaced=True
        record={'version':candidate,'tag':release['tag_name'],'asset':asset['name'],'sha256':sha.hexdigest()}
        fd,tmp=tempfile.mkstemp(prefix='.release-meta-',dir=root)
        try:
            with os.fdopen(fd,'w') as out:json.dump(record,out,indent=2);out.flush();os.fsync(out.fileno())
            os.replace(tmp,metadata)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        logging.info('Downloaded Apollo Reborn %s GLASS with all extensions',candidate)
        return True
    except Exception:
        logging.exception('Apollo release update check failed; keeping the current IPA')
        # Invalidate prepared cache even if metadata persistence failed after replacement.
        return replaced
    finally:
        if temporary and os.path.exists(temporary):os.unlink(temporary)
