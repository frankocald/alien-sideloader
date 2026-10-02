#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Apollo Sideload contributors.
"""Deterministic launchd worker: signing, LAN/Tailscale install, Discord retries."""
import argparse, contextlib, datetime as dt, fcntl, json, logging, logging.handlers
import os, pathlib, plistlib, signal, subprocess, tempfile, time, urllib.error, urllib.parse, urllib.request, uuid, zipfile
from zoneinfo import ZoneInfo
from apollo_release_updater import update as update_release

ROOT = pathlib.Path.home()/'Library/Application Support/ApolloSideload'
from identity import targets, validate_identity, GROUP_TARGETS
DEVICE=None
TEAM=None
TARGETS={}
GROUP=None
DAY=86400

def atomic_json(path, data):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(data,f,indent=2);f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o600);os.replace(tmp,path)
        dfd=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(dfd)
        finally:os.close(dfd)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def run(command, timeout, log=None):
    with tempfile.TemporaryFile() as output:
        p=subprocess.Popen([str(x) for x in command],stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
        try:p.wait(timeout=timeout)
        except BaseException:
            with contextlib.suppress(ProcessLookupError):os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):os.killpg(p.pid,signal.SIGKILL)
                p.wait()
            raise
        output.seek(0);result=output.read().decode(errors='replace')
    if log:pathlib.Path(log).write_text(result)
    if p.returncode:raise RuntimeError('Command failed: '+pathlib.Path(command[0]).name+' (see operation log)')
    return result

def decode(data):
    with tempfile.NamedTemporaryFile() as f:
        f.write(data);f.flush()
        return plistlib.loads(subprocess.check_output(['/usr/bin/security','cms','-D','-i',f.name],stderr=subprocess.DEVNULL))

def profile_expiry(base):
    values=[]
    for name,bundle in TARGETS.items():
        p=decode((base/'apollo-signing-profiles'/(name+'.mobileprovision')).read_bytes())
        if p['Entitlements']['application-identifier']!=TEAM+'.'+bundle:
            raise RuntimeError('Profile identity changed: '+name)
        values.append(p['ExpirationDate'].replace(tzinfo=dt.timezone.utc).timestamp())
    return min(values)

def validate_ipa(path):
    """Fail closed on identity changes; updates always replace the same app."""
    found={};expiries=[]
    with zipfile.ZipFile(path) as z:
        infos=[n for n in z.namelist() if n.startswith('Payload/') and
               (n.count('/')==2 or (n.count('/')==4 and '/PlugIns/' in n)) and n.endswith('/Info.plist')]
        for info in infos:
            directory=info.rsplit('/',1)[0];name=pathlib.PurePosixPath(directory).stem
            found[name]=plistlib.loads(z.read(info))['CFBundleIdentifier']
            p=decode(z.read(directory+'/embedded.mobileprovision'))
            ent=p['Entitlements']
            if ent.get('application-identifier')!=TEAM+'.'+found[name]:raise RuntimeError('Signing identity changed')
            expected_groups={GROUP} if name in GROUP_TARGETS else set()
            if set(ent.get('com.apple.security.application-groups',[]))!=expected_groups:raise RuntimeError('App group changed')
            if ent.get('keychain-access-groups') not in [[TEAM+'.*'],[TEAM+'.'+TARGETS['Apollo']]]:raise RuntimeError('Shared keychain profile changed')
            expiries.append(p['ExpirationDate'].replace(tzinfo=dt.timezone.utc).timestamp())
    if found!=TARGETS:raise RuntimeError('App or extension bundle IDs changed; install refused to preserve data')
    return min(expiries)

class Discord:
    def __init__(self,config):self.config=config
    def request(self,method,path,data=None):
        # Credentials are a private file, never command arguments or log contents.
        token=json.loads(pathlib.Path(self.config['credentials']).read_text())['token']
        body=None if data is None else json.dumps(data).encode()
        req=urllib.request.Request('https://discord.com/api/v10/'+path,data=body,method=method,
            headers={'Authorization':'Bot '+token,'Content-Type':'application/json','User-Agent':'ApolloSideload/1.0'})
        with urllib.request.urlopen(req,timeout=15) as r:
            raw=r.read();return json.loads(raw) if raw else None
    def send(self,item):
        return self.request('POST','channels/'+self.config['channel']+'/messages',
            {'content':item['text'],'nonce':item['id'],'enforce_nonce':True,'allowed_mentions':{'parse':[]}})['id']
    def check(self,message):
        self.request('PUT','channels/'+self.config['channel']+'/messages/'+message+'/reactions/'+urllib.parse.quote('✅',safe='')+'/@me')
    def reactions(self,message):
        base='channels/'+self.config['channel']+'/messages/'+message
        m=self.request('GET',base);present=set()
        for r in m.get('reactions',[]):
            e=r['emoji'];emoji=e['name']+(':'+e['id'] if e.get('id') else '')
            cursor=None
            while True:
                query='?limit=100'+('&after='+cursor if cursor else '')
                users=self.request('GET',base+'/reactions/'+urllib.parse.quote(emoji,safe='')+query)
                for u in users:
                    if not u.get('bot') and u['id']==self.config['user']:present.add(emoji+'|'+u['id'])
                if len(users)<100:break
                cursor=users[-1]['id']
        return present

class Worker:
    def __init__(self,root,clock=time.time,discord=None):
        self.root=pathlib.Path(root);self.clock=clock
        self.config=json.loads((self.root/'config.json').read_text());self.base=pathlib.Path(self.config['assets'])
        global DEVICE, TEAM, TARGETS, GROUP
        signing=validate_identity(self.config['signing'])
        DEVICE=signing['device'];TEAM=signing['team'];TARGETS=targets(signing['bundle_id']);GROUP=signing['group']
        self.path=self.root/'state.json';self.state=json.loads(self.path.read_text())
        self.discord=discord or (Discord(self.config['discord']) if self.config.get('discord') else None)
    def save(self):atomic_json(self.path,self.state)
    def queue(self,text,kind='info',cycle=None,message=None):
        if self.discord is None:logging.info('%s',text);return
        # Coalesce unsent failure alerts, retaining the newest reason.
        if kind=='failure':
            for item in self.state['outbox']:
                if item['kind']==kind and item.get('cycle')==cycle:item['text']=text;self.save();return
        self.state['outbox'].append({'id':uuid.uuid4().hex[:24],'text':text,'kind':kind,'cycle':cycle,'message':message,'next':0,'attempts':0})
        self.save()
    def flush(self):
        if self.discord is None:return
        now=self.clock()
        for item in list(self.state['outbox']):
            if now<item['next']:continue
            try:
                if item['kind']=='success_check':
                    target=item.get('message') or self.state.get('last_message')
                    if target:self.discord.check(target)
                    message=None
                else:message=self.discord.send(item)
            except Exception:
                item['attempts']+=1;item['next']=now+min(3600,60*2**min(item['attempts'],6));self.save()
                logging.warning('Discord unavailable; notification remains queued');break
            pending=self.state.get('pending')
            if message:
                self.state['last_message']=message
                if pending and item['cycle']==pending['id']:pending['last_message']=message
            if item['kind']=='failure' and pending and item['cycle']==pending['id']:
                pending['message']=message;pending['reactions']=[]
            self.state['outbox'].remove(item);self.save()
    def new_cycle(self):
        self.state['pending']={'id':uuid.uuid4().hex,'auto_attempts':0,'next_auto':self.clock(),
                               'message':None,'reactions':[],'ready':None,'reaction_requested':False,'cycle_attempts':0}
        self.save()
    def allowed(self,source='automatic'):
        now=self.clock();recent=[t for t in self.state.get('attempts',[]) if t>now-DAY]
        self.state['attempts']=recent
        return len(recent)<8 and (source=='reaction' or sum(t>now-3600 for t in recent)<4)
    def retry_time(self,source):
        now=self.clock();recent=sorted(t for t in self.state['attempts'] if t>now-DAY)
        times=[now]
        if len(recent)>=8:times.append(recent[-8]+DAY)
        hour=[t for t in recent if t>now-3600]
        if source!='reaction' and len(hour)>=4:times.append(hour[-4]+3600)
        return dt.datetime.fromtimestamp(max(times),dt.datetime.now().astimezone().tzinfo).strftime('%-I:%M:%S %p %Z')
    def poll(self):
        if self.discord is None:return
        p=self.state.get('pending')
        if not p or not p['message']:return
        try:present=self.discord.reactions(p['message'])
        except urllib.error.HTTPError as e:
            if e.code==404:
                p['message']=None;self.state.pop('alert_update',None);self.save()
                self.alert('The previous retry message was deleted.');return
            logging.warning('Reaction polling unavailable');return
        except Exception:logging.warning('Reaction polling unavailable');return
        added=present-set(p['reactions']);p['reactions']=sorted(present)
        if added:
            p['reaction_requested']=True;p['request_source']='reaction';p['deferred_notice']=False
        self.save()
    def alert(self,reason,manual=False):
        p=self.state['pending'];expiry=self.state['installed_expiry']
        deadline=dt.datetime.fromtimestamp(expiry,dt.timezone.utc).isoformat()
        text=('Apollo retry '+reason[0].lower()+reason[1:] if manual else reason+' Installed profiles expire '+deadline+'.')
        text+=(' React to this message to retry.' if self.discord else ' Run the worker with --run-now to retry.')
        # The newly delivered failure becomes the only reaction target.
        p['message']=None;p['reactions']=[];self.state.pop('alert_update',None)
        self.queue(text,'failure',p['id'])
    def update_alert(self):
        if self.discord is None:return
        item=self.state.get('alert_update')
        if not item or self.clock()<item['next']:return
        try:self.discord.request('PATCH','channels/'+self.config['discord']['channel']+'/messages/'+item['message'],
                                {'content':item['text'],'allowed_mentions':{'parse':[]}})
        except Exception:item['next']=self.clock()+300;self.save();return
        self.state.pop('alert_update',None);self.save()
    def prepare(self):
        p=self.state['pending'];ipa=self.root/'prepared.ipa';now=self.clock()
        self.state['stage']='release update';self.save()
        if update_release(self.root):p['ready']=None;self.save()
        if p.get('ready') and ipa.exists() and validate_ipa(ipa)>now+2*DAY:return ipa
        self.state['stage']='profile renewal';self.save()
        expiry=profile_expiry(self.base)
        if expiry<=self.state['installed_expiry'] or expiry<now+6*DAY:
            run(['/usr/bin/python3',self.base/'renew-apollo-profiles.py','--config',self.root/'config.json'],1800,self.root/'logs/renew.log')
        expiry=profile_expiry(self.base)
        if expiry<=self.state['installed_expiry'] or expiry<now+6*DAY:raise RuntimeError('All eight profiles must gain fresh validity')
        self.state['stage']='signing';self.save()
        run(['/usr/bin/python3',self.base/'resign-apollo.py',self.root/'original.ipa','--output',ipa,'--config',self.root/'config.json'],300,self.root/'logs/sign.log')
        p['ready']=validate_ipa(ipa);self.save();return ipa
    def install(self,ipa):
        self.state['stage']='local network installation';self.save()
        with tempfile.TemporaryDirectory(prefix='apollo-install-') as tmp:
            root=pathlib.Path(tmp);run(['/usr/bin/ditto','-x','-k',ipa,root],60)
            apps=list((root/'Payload').glob('*.app'))
            if len(apps)!=1:raise RuntimeError('Expected one app')
            run(['/usr/bin/codesign','--verify','--deep','--strict',apps[0]],60)
            for bundle in [apps[0],*apps[0].glob('PlugIns/*.appex')]:
                ent=plistlib.loads(subprocess.check_output(['/usr/bin/codesign','-d','--entitlements',':-',str(bundle)],stderr=subprocess.DEVNULL))
                if ent.get('keychain-access-groups')!=[TEAM+'.'+TARGETS['Apollo']]:
                    raise RuntimeError('Signed shared keychain changed; installation refused')
            try:
                devices=root/'devices.json'
                run(['/usr/bin/xcrun','devicectl','list','devices','--timeout','10','--json-output',devices],15)
                rows=json.loads(devices.read_text())['result']['devices']
                device=next(d for d in rows if d['identifier']==DEVICE)
                if device.get('connectionProperties',{}).get('transportType')!='localNetwork':raise RuntimeError('No local network route')
                run(['/usr/bin/xcrun','devicectl','device','install','app','--device',DEVICE,'--timeout','90',apps[0]],105,self.root/'logs/local-install.log')
                return 'local network'
            except Exception:logging.info('Local route unsuccessful; trying Tailscale')
            self.state['stage']='Tailscale installation';self.save()
            if not self.config.get('bridge_profile'):raise RuntimeError('No local route; optional Tailscale bridge is not configured')
            profile=self.config['bridge_profile'];bridge=self.base/'tailscale-bridge/ios-ota'
            status=json.loads(run([bridge,'status','--profile',profile],15))
            if status.get('state') not in ['active','recovering']:raise RuntimeError('No usable Apple tunnel over Tailscale')
            output=run([bridge,'install','--profile',profile,apps[0]],360,self.root/'logs/tailscale-install.log')
            if not any(json.loads(line).get('event')=='installed' for line in output.splitlines() if line.startswith('{')):
                raise RuntimeError('Installation completion not confirmed')
            return 'Tailscale'
    def attempt(self,source):
        p=self.state['pending'];now=self.clock()
        # Existing pending cycles created before this field was introduced are
        # retries when they already have an alert. Reaction requests always are.
        is_retry=source=='reaction' or p.get('cycle_attempts',0)>0 or bool(p.get('message'))
        p['cycle_attempts']=p.get('cycle_attempts',0)+1
        self.state['attempts'].append(now);self.state['attempting']=True
        p['reaction_requested']=False
        p['deferred_notice']=False
        if source=='automatic':p['auto_attempts']+=1
        # Persist before contacting Xcode/phone so a crash cannot reset the retry budget.
        self.save()
        if is_retry:
            stamp=dt.datetime.fromtimestamp(now,dt.datetime.now().astimezone().tzinfo).strftime('%-I:%M:%S %p %Z')
            prefix='Your reaction was received. ' if source=='reaction' else ''
            self.queue(prefix+'Apollo retry started at '+stamp+'.',
                       'retry_started',p['id'])
            self.flush()
        try:
            ipa=self.prepare();route=self.install(ipa);expiry=validate_ipa(ipa)
        except Exception:
            stage=self.state.get('stage','operation');logging.exception('Sideload attempt failed during %s',stage)
            delays=[900,3600,14400]
            p['next_auto']=self.clock()+delays[min(max(p['auto_attempts']-1,0),2)]
            self.state['attempting']=False;self.state['last_error']=stage;self.save()
            self.alert('Failed during '+stage+'.',manual=source!='automatic')
            return False
        self.state['installed_expiry']=expiry;self.state['last_success']=self.clock()
        self.state['last_route']=route;self.state['attempting']=False;self.state['pending']=None
        self.state['outbox']=[x for x in self.state['outbox'] if not (x.get('cycle')==p['id'] and x['kind']=='failure')]
        self.state.pop('alert_update',None)
        message=p.get('last_message') or p.get('message') or self.state.get('last_message')
        unpublished=any(x.get('cycle')==p['id'] and x['kind']!='success_check' for x in self.state['outbox'])
        if message or unpublished:self.queue('','success_check',p['id'],message=None if unpublished else message)
        self.save();logging.info('Install succeeded over %s; expiry=%s',route,expiry);return True
    def tick(self,force=False,fresh=False):
        if fresh:
            previous=self.state.get('pending')
            if previous:
                self.state['outbox']=[x for x in self.state['outbox'] if not (x.get('cycle')==previous['id'] and x['kind']=='failure')]
                if previous.get('message'):
                    self.state['alert_update']={'message':previous['message'],'text':'This retry request was cancelled. A fresh manual test is starting.','next':0}
            self.state['pending']=None;self.state['attempting']=False;self.save()
            force=True
        if self.state.get('attempting'):
            self.state['attempting']=False
            if self.state.get('pending'):self.state['pending']['next_auto']=self.clock()+900
            self.save();self.alert('The previous attempt was interrupted; retry state was recovered.')
        self.flush();self.update_alert();self.poll()
        now=self.clock();due=min(self.state['last_success']+6*DAY,self.state['installed_expiry']-DAY)
        if not self.state.get('pending') and (force or now>=due):self.new_cycle()
        p=self.state.get('pending')
        if p and force:
            # A manual request must survive rate limiting and a process exit.
            p['reaction_requested']=True;p['request_source']='manual';self.save()
        source=p.get('request_source','reaction') if p and p.get('reaction_requested') else 'automatic'
        if p and (self.allowed(source) or fresh):
            if force or p.get('reaction_requested'):self.attempt(source)
            elif p['auto_attempts']<3 and now>=p['next_auto']:self.attempt('automatic')
        elif p and p.get('reaction_requested') and not p.get('deferred_notice'):
            p['deferred_notice']=True
            prefix='Your reaction was received. ' if source=='reaction' else 'Retry request received. '
            self.queue(prefix+'Apollo retry is queued until '+self.retry_time(source)+
                       ' because the '+('daily' if source=='reaction' else 'retry')+' limit is active. I will acknowledge when it starts.',
                       'retry_queued',p['id'])
        self.save();self.flush();self.update_alert()

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=pathlib.Path,default=ROOT)
    ap.add_argument('--run-now',action='store_true');ap.add_argument('--status',action='store_true')
    ap.add_argument('--fresh-run',action='store_true',help='Cancel the pending cycle and run one explicitly requested manual test despite rate limits; retain attempt history')
    a=ap.parse_args()
    os.umask(0o077)
    # Turn launchd termination into an exception so run() terminates its process
    # group before releasing the job lock. Persistent 'attempting' marks recovery.
    def terminate(signum,frame):raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,terminate)
    if a.status:
        state=json.loads((a.root/'state.json').read_text())
        print(json.dumps(state,indent=2));return
    (a.root/'logs').mkdir(parents=True,exist_ok=True)
    handler=logging.handlers.RotatingFileHandler(a.root/'logs/worker.log',maxBytes=2_000_000,backupCount=3)
    logging.basicConfig(level=logging.INFO,handlers=[handler],format='%(asctime)s %(levelname)s %(message)s')
    lock=open(a.root/'job.lock','a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:return
    try:Worker(a.root).tick(force=a.run_now,fresh=a.fresh_run)
    except Exception:logging.exception('Worker failed; persistent state retained');raise

if __name__=='__main__':main()
