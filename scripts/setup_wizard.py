#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Apollo Sideload contributors.
"""Create an isolated private runtime and optional launchd schedule."""
import argparse,datetime as dt,getpass,hashlib,ipaddress,json,os,pathlib,plistlib,re,shutil,subprocess,sys,tempfile
from identity import targets, validate_identity, GROUP_TARGETS, OLD_GROUP
SOURCE=pathlib.Path(__file__).resolve().parent
LABEL='io.github.apollo-sideload.worker'
DEFAULT=pathlib.Path.home()/'Library/Application Support/ApolloSideload'

def private_json(path,data):
    path=pathlib.Path(path)
    with path.open('w') as out:json.dump(data,out,indent=2)
    path.chmod(0o600)

def suggest_group(bundle_id):
    prefix='group.app.apollo.'
    return prefix+hashlib.sha256(bundle_id.encode()).hexdigest()[:len(OLD_GROUP)-len(prefix)]

def project_files(directory,name,identity):
    """Minimal Objective-C placeholder project solely for Xcode provisioning."""
    directory.mkdir(parents=True)
    main=name=='Apollo';bundle=targets(identity['bundle_id'])[name]
    ent={'keychain-access-groups':['$(AppIdentifierPrefix)'+identity['bundle_id']]}
    if name in GROUP_TARGETS:ent['com.apple.security.application-groups']=[identity['group']]
    info={'CFBundleIdentifier':'$(PRODUCT_BUNDLE_IDENTIFIER)','CFBundleExecutable':'$(EXECUTABLE_NAME)',
          'CFBundleName':'$(PRODUCT_NAME)','CFBundlePackageType':'APPL' if main else 'XPC!',
          'CFBundleShortVersionString':'1.0','CFBundleVersion':'1','MinimumOSVersion':'15.0'}
    if not main:info['NSExtension']={'NSExtensionPointIdentifier':'com.apple.intents-service','NSExtensionPrincipalClass':'NSObject'}
    for filename,data in [('Signing.entitlements',ent),('Info.plist',info)]:
        (directory/filename).write_bytes(plistlib.dumps(data));(directory/filename).chmod(0o600)
    (directory/'Placeholder.m').write_text('#import <Foundation/Foundation.h>\n'+('int main(int argc, char **argv) { return 0; }\n' if main else '@interface Placeholder : NSObject @end\n@implementation Placeholder @end\n'))
    ids={key:hashlib.sha256((name+key).encode()).hexdigest()[:24].upper() for key in ['project','group','products','target','product','source','buildsource','sources','frameworks','resources','projectconfigs','targetconfigs','projectdebug','projectrelease','targetdebug','targetrelease']}
    o={}
    def put(key,isa,**fields):o[ids[key]]=dict(isa=isa,**fields)
    put('project','PBXProject',buildConfigurationList=ids['projectconfigs'],mainGroup=ids['group'],productRefGroup=ids['products'],targets=[ids['target']],compatibilityVersion='Xcode 14.0',developmentRegion='en',knownRegions=['en','Base'],projectDirPath='',projectRoot='',attributes={'TargetAttributes':{ids['target']:{'SystemCapabilities':{'com.apple.ApplicationGroups.iOS':{'enabled':1}}}}})
    put('group','PBXGroup',children=[ids['source'],ids['products']],sourceTree='<group>')
    put('products','PBXGroup',children=[ids['product']],name='Products',sourceTree='<group>')
    put('source','PBXFileReference',path='Placeholder.m',lastKnownFileType='sourcecode.c.objc',sourceTree='<group>')
    put('product','PBXFileReference',path=name+('.app' if main else '.appex'),explicitFileType='wrapper.application' if main else 'wrapper.app-extension',sourceTree='BUILT_PRODUCTS_DIR',includeInIndex=0)
    put('buildsource','PBXBuildFile',fileRef=ids['source'])
    for key,kind in [('sources','PBXSourcesBuildPhase'),('frameworks','PBXFrameworksBuildPhase'),('resources','PBXResourcesBuildPhase')]:
        put(key,kind,buildActionMask=2147483647,files=[ids['buildsource']] if key=='sources' else [],runOnlyForDeploymentPostprocessing=0)
    put('target','PBXNativeTarget',name=name,productName=name,productReference=ids['product'],productType='com.apple.product-type.application' if main else 'com.apple.product-type.app-extension',buildConfigurationList=ids['targetconfigs'],buildPhases=[ids[k] for k in ['sources','frameworks','resources']],buildRules=[],dependencies=[])
    for scope in ['project','target']:
        put(scope+'configs','XCConfigurationList',buildConfigurations=[ids[scope+'debug'],ids[scope+'release']],defaultConfigurationIsVisible=0,defaultConfigurationName='Release')
        for mode in ['debug','release']:
            settings={'DEVELOPMENT_TEAM':identity['team'],'SDKROOT':'iphoneos','IPHONEOS_DEPLOYMENT_TARGET':'15.0','CLANG_ENABLE_MODULES':'YES','CLANG_ENABLE_OBJC_ARC':'YES'}
            if scope=='target':settings.update(PRODUCT_BUNDLE_IDENTIFIER=bundle,PRODUCT_NAME='$(TARGET_NAME)',CODE_SIGN_STYLE='Automatic',CODE_SIGN_ENTITLEMENTS='Signing.entitlements',INFOPLIST_FILE='Info.plist',GENERATE_INFOPLIST_FILE='NO',TARGETED_DEVICE_FAMILY='1,2',APPLICATION_EXTENSION_API_ONLY='NO' if main else 'YES',SKIP_INSTALL='NO')
            put(scope+mode,'XCBuildConfiguration',name=mode.title(),buildSettings=settings)
    project=directory/'Signing.xcodeproj';project.mkdir()
    private_json(project/'project.pbxproj',{'archiveVersion':'1','objectVersion':'56','classes':{},'objects':o,'rootObject':ids['project']})

def create_runtime(root,identity,discord=None):
    root=pathlib.Path(root).expanduser().resolve()
    if root.exists():raise FileExistsError('Runtime already exists; use --resume or choose a different --root. No existing installation is overwritten.')
    validate_identity(identity)
    root.parent.mkdir(parents=True,exist_ok=True)
    stage=pathlib.Path(tempfile.mkdtemp(prefix='.apollo-setup-',dir=root.parent))
    try:
        assets=stage/'assets';assets.mkdir();(stage/'logs').mkdir();(stage/'bridge').mkdir()
        for src in SOURCE.glob('*.py'):shutil.copy2(src,assets/src.name)
        for name in targets(identity['bundle_id']):project_files(assets/'ApolloSigning'/name,name,identity)
        config={'assets':str(root/'assets'),'signing':dict(identity),'discord':None,'bridge_profile':None}
        if discord:
            if not str(discord['channel']).isdigit() or not str(discord['user']).isdigit() or not discord['token']:raise ValueError('Discord channel/user IDs and bot token are required')
            private_json(stage/'discord-credentials.json',{'token':discord['token']})
            config['discord']={'channel':discord['channel'],'user':discord['user'],'credentials':str(root/'discord-credentials.json')}
        private_json(stage/'config.json',config)
        private_json(stage/'release.json',{'version':'0.0.0'})
        private_json(stage/'state.json',{'last_success':0,'installed_expiry':0,'attempts':[],'pending':None,'outbox':[]})
        for file in stage.rglob('*'):file.chmod(0o700 if file.is_dir() else 0o600)
        stage.chmod(0o700);os.rename(stage,root)
        return config
    finally:
        if stage.exists():shutil.rmtree(stage)

def launch_agent(root):
    root=pathlib.Path(root).expanduser().resolve()
    return {'Label':LABEL,'ProgramArguments':['/usr/bin/python3',str(root/'assets/apollo-sideload-job.py'),'--root',str(root)],'RunAtLoad':True,'StartInterval':10,'ProcessType':'Background','StandardOutPath':str(root/'logs/launchd.log'),'StandardErrorPath':str(root/'logs/launchd-error.log')}

def choose(title,items,label):
    if not items:raise RuntimeError('No '+title+' found. Follow the prerequisites in README.md.')
    print('\nChoose '+title+':')
    for n,item in enumerate(items,1):print(str(n)+'. '+label(item))
    if len(items)==1:return items[0]
    while True:
        answer=input('Number: ').strip()
        if answer.isdigit() and 1<=int(answer)<=len(items):return items[int(answer)-1]

def ask(prompt,default=None):
    value=input(prompt+(' ['+default+']' if default else '')+': ').strip()
    return value or default or ''
def yes(prompt):return ask(prompt+' (y/N)').lower() in ['y','yes']

def profiles_ready(root,identity):
    try:
        for name,bundle in targets(identity['bundle_id']).items():
            file=root/'assets/apollo-signing-profiles'/(name+'.mobileprovision')
            if not file.is_file():return False
            profile=plistlib.loads(subprocess.check_output(['/usr/bin/security','cms','-D','-i',str(file)],stderr=subprocess.DEVNULL,timeout=15))
            if profile['ExpirationDate']<dt.datetime.utcnow()+dt.timedelta(hours=144):return False
            if identity['udid'] not in profile.get('ProvisionedDevices',[]):return False
            if identity['certificate'].lower() not in [hashlib.sha1(c).hexdigest() for c in profile['DeveloperCertificates']]:return False
            ent=profile['Entitlements']
            if ent['application-identifier']!=identity['team']+'.'+bundle:return False
            if set(ent.get('com.apple.security.application-groups',[]))!=({identity['group']} if name in GROUP_TARGETS else set()):return False
        return True
    except Exception:return False

def prerequisites():
    if sys.platform!='darwin':raise RuntimeError('Setup requires macOS and full Xcode.')
    subprocess.run(['/usr/bin/xcrun','--find','devicectl'],check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['/usr/bin/xcodebuild','-version'],check=True)

def collect_identity():
    raw=subprocess.check_output(['/usr/bin/security','find-identity','-v','-p','codesigning'],text=True)
    certs=[{'certificate':m[0],'name':m[1]} for m in re.findall(r'\d+\) ([A-Fa-f0-9]{40}) "([^"]+)"',raw) if m[1].startswith(('Apple Development:','iPhone Developer:'))]
    cert=choose('development signing certificate',certs,lambda c:c['name'])
    matched=re.search(r'\(([A-Z0-9]{10})\)$',cert['name'])
    team=ask('Apple Team ID (Xcode → Settings → Accounts)',matched.group(1) if matched else None)
    with tempfile.TemporaryDirectory() as tmp:
        data=pathlib.Path(tmp)/'devices.json'
        subprocess.run(['/usr/bin/xcrun','devicectl','list','devices','--timeout','10','--json-output',str(data)],check=True)
        rows=json.loads(data.read_text())['result']['devices']
    device=choose('paired iPhone',rows,lambda d:d.get('deviceProperties',{}).get('name',d['identifier']))
    udid=device.get('hardwareProperties',{}).get('udid') or ask('iPhone UDID (Xcode Devices and Simulators)')
    print('For an existing sideloaded Apollo, enter its EXACT bundle ID and shared group to retain its data. Changing them creates a different installation.')
    bundle=ask('Your unique bundle ID, e.g. org.yourname.Apollo')
    group=ask('Shared app group ('+str(len(OLD_GROUP))+' ASCII bytes)',suggest_group(bundle))
    identity={'team':team,'certificate':cert['certificate'],'device':device['identifier'],'udid':udid,'bundle_id':bundle,'group':group}
    return validate_identity(identity)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=pathlib.Path,default=DEFAULT)
    parser.add_argument('--resume',action='store_true',help='Continue an incomplete setup without changing its identity')
    args=parser.parse_args();root=args.root.expanduser().resolve();os.umask(0o077)
    prerequisites()
    print('This wizard uses your existing Xcode account and development certificate. Apple credentials stay in Xcode/Keychain. It never uninstalls Apollo or revokes certificates.')
    if args.resume:
        config=json.loads((root/'config.json').read_text());validate_identity(config['signing'])
    else:
        identity=collect_identity();discord=None
        if yes('Enable optional Discord failure notifications and reaction retries?'):
            print('Use a dedicated bot; grant View Channel, Send Messages, Read Message History and Add Reactions in one channel. No administrator permission is needed.')
            discord={'channel':ask('Discord channel ID'),'user':ask('Your Discord user ID'),'token':getpass.getpass('Bot token (hidden): ')}
        config=create_runtime(root,identity,discord)
    import apollo_release_updater
    print('Fetching the latest stable GLASS IPA with all extensions from the official Apollo Reborn GitHub release. This trusts upstream executable code; checksum validation cannot prove it is harmless.')
    apollo_release_updater.update(root)
    if not (root/'original.ipa').exists():raise RuntimeError('IPA download failed. Fix connectivity and repeat with --resume. See terminal/log output.')
    print('Requesting eight provisioning profiles. Xcode may show account or Keychain prompts. No placeholder app is installed.')
    if not profiles_ready(root,config['signing']):
        subprocess.run(['/usr/bin/python3',str(root/'assets/renew-apollo-profiles.py'),'--config',str(root/'config.json')],check=True)
    if yes('Configure optional Tailscale remote installation?'):
        configure_bridge(root,config)
    print('Setup complete. A first run signs Apollo and installs over its configured identity; export an Apollo backup before the first installation.')
    if yes('Enable automatic signing and installation every six days?'):
        agent=pathlib.Path.home()/'Library/LaunchAgents'/(LABEL+'.plist')
        if agent.exists():raise FileExistsError('Schedule already exists; inspect it before replacing it.')
        agent.parent.mkdir(parents=True,exist_ok=True);agent.write_bytes(plistlib.dumps(launch_agent(root)));agent.chmod(0o600)
        subprocess.run(['/bin/launchctl','bootstrap','gui/'+str(os.getuid()),str(agent)],check=True)
        print('Schedule enabled; first attempt starts immediately. Discord is '+('enabled' if config['discord'] else 'disabled; check logs for failures')+'.')
    else:print('Run manually: /usr/bin/python3 "'+str(root/'assets/apollo-sideload-job.py')+'" --root "'+str(root)+'" --run-now')


def import_pairing(root,config,record,ip):
    record=pathlib.Path(record).expanduser()
    if record.is_symlink() or not record.is_file() or record.stat().st_mode&0o077 or record.stat().st_uid!=os.getuid():raise ValueError('Pairing record must be your owner-only regular file')
    address=ipaddress.ip_address(ip)
    networks=[ipaddress.ip_network('100.64.0.0/10'),ipaddress.ip_network('fd7a:115c:a1e0::/48')]
    if not any(address in network for network in networks):raise ValueError('Use the iPhone Tailscale IP address')
    data=plistlib.loads(record.read_bytes())
    if data.get('peer_udid')!=config['signing']['udid']:raise ValueError('Pairing record belongs to another iPhone')
    for key in ['host_identifier','peer_identifier']:
        if not isinstance(data.get(key),str) or not data[key]:raise ValueError('Pairing record is missing verified identity: '+key)
    for key,size in [('private_key',32),('public_key',32),('peer_public_key',32),('host_alt_irk',16)]:
        if not isinstance(data.get(key),bytes) or len(data[key])!=size:raise ValueError('Pairing record is missing '+key+'; secure USB pinning is required')
    destination=pathlib.Path(root)/'bridge/pairing.plist';destination.parent.mkdir(parents=True,exist_ok=True);destination.parent.chmod(0o700)
    stage=destination.with_suffix('.staged')
    with stage.open('wb') as out:out.write(plistlib.dumps(data))
    stage.chmod(0o600);os.replace(stage,destination)
    return destination

def configure_bridge(root,config):
    print('Remote setup captures the phone public key through a trusted unlocked USB connection. Keep USB connected during setup.')
    if yes('Import an existing verified pairing record instead of creating one?'):
        record=ask('Path to owner-only pinned RemotePairing plist')
    else:
        python=shutil.which('python3.12') or ask('Path to Python 3.12 (install with brew install python@3.12 if needed)')
        if not python:raise RuntimeError('Python 3.12 is required only for optional USB pairing. LAN setup remains usable.')
        record=create_usb_pairing(root,config,python)
    ip=ask('iPhone Tailscale IP')
    pair=import_pairing(root,config,record,ip)
    source=SOURCE.parent/'bridge'
    if not source.is_dir():raise RuntimeError('Run remote setup from the downloaded source repository; bridge source is missing.')
    environment=dict(os.environ,LYO_NODUS_IOS_OTA_RUNTIME_ROOT=str(root/'bridge/build-runtime'))
    subprocess.run(['bash',str(source/'scripts/build.sh')],check=True,env=environment)
    binary=root/'assets/tailscale-bridge/ios-ota';binary.parent.mkdir(exist_ok=True)
    shutil.copy2(source/'.build/lyo-nodus-ios-ota',binary);binary.chmod(0o700)
    profile=root/'bridge/iphone.json';data=plistlib.loads(pair.read_bytes())
    subprocess.run([str(binary),'configure','--profile',str(profile),'--device-label','iPhone','--remote-identifier',data['peer_udid'],'--target-tailnet-ip',ip,'--pair-record',str(pair)],check=True)
    subprocess.run([str(binary),'doctor','--profile',str(profile)],check=True)
    subprocess.run([str(binary),'launch-agent','install','--profile',str(profile)],check=True)
    config['bridge_profile']=str(profile);private_json(root/'config.json',config)
    print('Connect the iPhone to any Wi-Fi and enable Tailscale. The bridge needs to report active before remote installation.')

def create_usb_pairing(root,config,python):
    venv=root/'bridge/pairing-venv'
    subprocess.run([python,'-m','venv',str(venv)],check=True,timeout=120)
    subprocess.run([str(venv/'bin/python'),'-m','pip','install','pymobiledevice3==11.12.4','cryptography==50.0.2'],check=True,timeout=300)
    record=root/'bridge/pairing.plist'
    subprocess.run([str(venv/'bin/python'),str(SOURCE/'pair_usb.py'),str(record),config['signing']['udid']],check=True,timeout=150)
    return record

if __name__=='__main__':
    try:main()
    except (Exception,KeyboardInterrupt) as error:print('Setup stopped: '+str(error),file=sys.stderr);raise SystemExit(1)
