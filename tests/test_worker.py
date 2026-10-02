#!/usr/bin/python3
import importlib.util,json,pathlib,tempfile,unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('job',pathlib.Path(__file__).resolve().parents[1]/'scripts/apollo-sideload-job.py')
j=importlib.util.module_from_spec(spec);spec.loader.exec_module(j)

class FakeDiscord:
    def __init__(self):self.offline=False;self.sent=[];self.present=set();self.edits=[];self.checks=[]
    def send(self,item):
        if self.offline:raise OSError('offline')
        self.sent.append(dict(item));return 'message-'+str(len(self.sent))
    def reactions(self,message):return self.present
    def request(self,*args):self.edits.append(args)
    def check(self,message):
        if self.offline:raise OSError('offline')
        self.checks.append(message)

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.now=2_000_000_000
        j.atomic_json(self.root/'release.json',{'version':'3.8.5'})
        j.atomic_json(self.root/'config.json',{'assets':str(self.root),'discord':{'user':'me','channel':'channel'},'signing':{'team':'TESTTEAM01','certificate':'1'*40,'device':'device-test','udid':'udid-test','bundle_id':'org.example.Apollo','group':'group.app.apollo.12345678901234'}})
        j.atomic_json(self.root/'state.json',{'last_success':self.now,'installed_expiry':self.now+7*j.DAY,'attempts':[],'pending':None,'outbox':[]})
        self.d=FakeDiscord();self.w=j.Worker(self.root,clock=lambda:self.now,discord=self.d)
    def tearDown(self):self.tmp.cleanup()
    def restart(self):return j.Worker(self.root,clock=lambda:self.now,discord=self.d)
    def test_new_release_invalidates_prepared_retry_cache(self):
        self.w.new_cycle();self.w.state['pending']['ready']=self.now+7*j.DAY
        (self.root/'prepared.ipa').write_bytes(b'old')
        with patch.object(j,'update_release',return_value=True),patch.object(j,'profile_expiry',side_effect=RuntimeError('stop before signing')):
            with self.assertRaises(RuntimeError):self.w.prepare()
        self.assertIsNone(self.restart().state['pending']['ready'])
    def test_unchanged_release_reuses_prepared_retry_cache(self):
        self.w.new_cycle();self.w.state['pending']['ready']=self.now+7*j.DAY
        (self.root/'prepared.ipa').write_bytes(b'old')
        with patch.object(j,'update_release',return_value=False) as check,patch.object(j,'validate_ipa',return_value=self.now+7*j.DAY),patch.object(j,'run') as command:
            self.assertEqual(self.w.prepare(),self.root/'prepared.ipa');check.assert_called_once_with(self.root);command.assert_not_called()
    def test_offline_notification_survives_restart_and_delivery(self):
        self.d.offline=True;self.w.queue('offline failure','failure','cycle');self.w.flush()
        w=self.restart();self.assertEqual(len(w.state['outbox']),1)
        self.now+=1000;self.d.offline=False;w.flush()
        self.assertEqual(w.state['outbox'],[]);self.assertEqual(len(self.d.sent),1)
    def test_any_emoji_once_and_remove_readd(self):
        self.w.new_cycle();p=self.w.state['pending'];p['message']='msg';self.w.save()
        for emoji in ['👍','❤️','custom:123']:
            self.d.present={emoji+'|me'};self.w.poll();self.assertTrue(p['reaction_requested'])
            p['reaction_requested']=False;self.w.save();self.w=self.restart();p=self.w.state['pending']
            self.w.poll();self.assertFalse(p['reaction_requested'])
            self.d.present=set();self.w.poll();self.d.present={emoji+'|me'};self.w.poll()
            self.assertTrue(p['reaction_requested']);p['reaction_requested']=False
    def test_four_hourly_eight_daily_limits_persist(self):
        self.w.state['attempts']=[self.now-i for i in range(4)];self.w.save()
        self.assertFalse(self.restart().allowed());self.now+=3601
        self.assertTrue(self.restart().allowed())
    def test_manual_request_survives_hourly_limit(self):
        self.w.new_cycle();self.w.state['attempts']=[self.now-i for i in range(4)];self.w.save()
        with patch.object(self.w,'attempt') as attempt:
            self.w.tick(force=True);attempt.assert_not_called()
        w=self.restart();self.assertTrue(w.state['pending']['reaction_requested'])
        self.now+=3601
        with patch.object(w,'attempt') as attempt:
            w.tick();attempt.assert_called_once_with('manual')
        self.w.state['attempts']=[self.now-i*3601 for i in range(8)];self.w.save()
        self.assertFalse(self.restart().allowed());self.now+=j.DAY
        self.assertTrue(self.restart().allowed())
    def test_three_automatic_attempts_then_wait_for_reaction(self):
        self.w.new_cycle();calls=[]
        def fail(source):
            calls.append(source);p=self.w.state['pending'];p['auto_attempts']+=1;p['next_auto']=self.now+900;self.w.save()
        with patch.object(self.w,'attempt',side_effect=fail):
            for i in range(5):self.w.tick();self.now+=3601
        self.assertEqual(calls,['automatic']*3)
    def test_interrupted_attempt_keeps_budget(self):
        self.w.new_cycle();self.w.state['attempting']=True;self.w.state['attempts']=[self.now];self.w.save()
        w=self.restart();w.tick();self.assertFalse(w.state['attempting'])
        self.assertEqual(w.state['attempts'],[self.now]);self.assertGreater(w.state['pending']['next_auto'],self.now)
        self.assertEqual(len(self.d.sent),1)
    def test_success_saves_expiry_and_resolves_alert(self):
        self.w.new_cycle();self.w.state['pending']['message']='msg';self.w.save()
        with patch.object(self.w,'prepare',return_value='ipa'),patch.object(self.w,'install',return_value='Tailscale'),patch.object(j,'validate_ipa',return_value=self.now+7*j.DAY):
            self.assertTrue(self.w.attempt('reaction'))
        w=self.restart();self.assertIsNone(w.state['pending']);self.assertEqual(w.state['last_route'],'Tailscale')
        w.flush();self.assertEqual(len(self.d.sent),1)
        self.assertIn('reaction was received',self.d.sent[0]['text'])
        self.assertEqual(self.d.checks,['message-1']);self.assertFalse(self.d.edits)
    def test_retry_failure_posts_new_message_and_rotates_target(self):
        self.w.new_cycle();self.w.state['pending']['message']='original';self.w.save()
        with patch.object(self.w,'prepare',side_effect=RuntimeError('offline')),patch.object(j.logging,'exception'):
            self.assertFalse(self.w.attempt('reaction'))
        w=self.restart();w.flush()
        self.assertEqual(w.state['pending']['message'],'message-2')
        self.assertEqual(len(self.d.sent),2)
        self.assertEqual(self.d.sent[-1]['text'],'Apollo retry failed during operation. React to this message to retry.')
    def test_automatic_retry_reports_outcome(self):
        self.w.new_cycle();self.w.state['pending']['cycle_attempts']=1;self.w.save()
        with patch.object(self.w,'prepare',return_value='ipa'),patch.object(self.w,'install',return_value='local network'),patch.object(j,'validate_ipa',return_value=self.now+7*j.DAY):
            self.w.attempt('automatic')
        self.w.flush();self.assertEqual(self.d.checks,['message-1']);self.assertEqual(len(self.d.sent),1)
    def test_offline_retry_results_survive_later_success_and_restart(self):
        self.w.new_cycle();p=self.w.state['pending'];self.d.offline=True
        self.w.queue('Earlier retry failed.','retry_result',p['id'])
        self.w.queue('Obsolete alert.','failure',p['id'])
        with patch.object(self.w,'prepare',return_value='ipa'),patch.object(self.w,'install',return_value='Tailscale'),patch.object(j,'validate_ipa',return_value=self.now+7*j.DAY):
            self.w.attempt('reaction')
        w=self.restart();self.assertEqual([x['kind'] for x in w.state['outbox']],['retry_result','retry_started','success_check'])
        w.flush();self.now+=1000;self.d.offline=False;w=self.restart();w.flush()
        self.assertEqual(len(self.d.sent),2);self.assertEqual(w.state['outbox'],[])
        self.assertEqual(self.d.checks,['message-2'])
    def test_automatic_failure_uses_short_expiry_template(self):
        self.w.new_cycle();self.w.state['stage']='Tailscale installation'
        with patch.object(self.w,'prepare',side_effect=RuntimeError('offline')),patch.object(j.logging,'exception'):
            self.w.attempt('automatic')
        self.w.flush();deadline=j.dt.datetime.fromtimestamp(self.w.state['installed_expiry'],j.dt.timezone.utc).isoformat()
        self.assertEqual(self.d.sent[-1]['text'],'Failed during Tailscale installation. Installed profiles expire '+deadline+'. React to this message to retry.')
    def test_success_reaction_persists_through_discord_outage(self):
        self.w.queue('','success_check',message='latest-message');self.d.offline=True;self.w.flush()
        w=self.restart();self.assertEqual(len(w.state['outbox']),1)
        self.now+=1000;self.d.offline=False;w.flush();self.assertEqual(self.d.checks,['latest-message'])
    def test_reaction_bypasses_hourly_limit(self):
        self.w.new_cycle();p=self.w.state['pending'];p['reaction_requested']=True;p['request_source']='reaction'
        self.w.state['attempts']=[self.now-i for i in range(5)];self.w.save()
        with patch.object(self.w,'attempt') as attempt:
            self.w.tick();attempt.assert_called_once_with('reaction')
    def test_daily_cap_queues_reaction_acknowledgement_once(self):
        self.w.new_cycle();p=self.w.state['pending'];p['reaction_requested']=True;p['request_source']='reaction'
        self.w.state['attempts']=[self.now-i*3601 for i in range(8)];self.w.save()
        with patch.object(self.w,'attempt') as attempt:
            self.w.tick();self.w.tick();attempt.assert_not_called()
        self.assertEqual(len(self.d.sent),1);self.assertIn('reaction was received',self.d.sent[0]['text'])
        self.assertIn('daily limit',self.d.sent[0]['text']);self.assertTrue(p['reaction_requested'])
    def test_start_acknowledgement_precedes_installation(self):
        self.w.new_cycle()
        def prepare():
            self.assertEqual(len(self.d.sent),1)
            self.assertEqual(self.d.sent[0]['kind'],'retry_started')
            return 'ipa'
        with patch.object(self.w,'prepare',side_effect=prepare),patch.object(self.w,'install',return_value='Tailscale'),patch.object(j,'validate_ipa',return_value=self.now+7*j.DAY):
            self.w.attempt('reaction')
    def test_six_day_schedule_and_expiry_override(self):
        with patch.object(self.w,'attempt') as attempt:
            self.w.tick();attempt.assert_not_called()
            self.now+=6*j.DAY;self.w.tick();attempt.assert_called_once_with('automatic')
        self.w.state['pending']=None;self.w.state['last_success']=self.now;self.w.state['installed_expiry']=self.now+12*3600
        with patch.object(self.w,'attempt') as attempt:self.w.tick();attempt.assert_called_once()
    def test_fresh_run_cancels_old_request_keeps_history(self):
        self.w.new_cycle();old=self.w.state['pending']['id'];self.w.state['pending']['message']='old-alert'
        self.w.state['pending']['reaction_requested']=True
        self.w.state['attempts']=[self.now-i for i in range(4)];self.w.save()
        with patch.object(self.w,'attempt') as attempt:
            self.w.tick(fresh=True);attempt.assert_called_once()
        self.assertNotEqual(self.w.state['pending']['id'],old)
        self.assertIsNone(self.w.state['pending']['message'])
        self.assertEqual(len(self.w.state['attempts']),4)
        self.assertTrue(self.d.edits)
    def test_identity_changes_fail_before_install(self):
        import zipfile,plistlib
        ipa=self.root/'wrong.ipa'
        with zipfile.ZipFile(ipa,'w') as z:
            z.writestr('Payload/Other.app/Info.plist',plistlib.dumps({'CFBundleIdentifier':'different'}))
            z.writestr('Payload/Other.app/embedded.mobileprovision',b'profile')
        with patch.object(j,'decode',return_value={'Entitlements':{'application-identifier':'OTHER.different'}}):
            with self.assertRaises(RuntimeError):j.validate_ipa(ipa)
    def test_lan_failure_falls_back_without_uninstall(self):
        self.w.new_cycle();self.w.config['bridge_profile']='private-profile';calls=[]
        def command(args,timeout,log=None):
            args=[str(a) for a in args];calls.append(args)
            if args[0]=='/usr/bin/ditto':
                (pathlib.Path(args[-1])/'Payload/Apollo.app').mkdir(parents=True);return ''
            if 'list' in args:
                target=pathlib.Path(args[args.index('--json-output')+1]);target.write_text(json.dumps({'result':{'devices':[]}}));return ''
            if 'status' in args:return json.dumps({'state':'active'})
            if 'install' in args:return json.dumps({'event':'installed'})
            return ''
        with patch.object(j,'run',side_effect=command),patch.object(j.subprocess,'check_output',return_value=j.plistlib.dumps({'keychain-access-groups':['TESTTEAM01.org.example.Apollo']})):
            self.assertEqual(self.w.install('ipa'),'Tailscale')
        self.assertFalse(any('uninstall' in c for c in calls))
        self.assertTrue(any('status' in c for c in calls));self.assertTrue(any('install' in c for c in calls))
    def test_profiles_with_unchanged_expiry_are_rejected(self):
        self.w.new_cycle()
        with patch.object(j,'profile_expiry',return_value=self.w.state['installed_expiry']),patch.object(j,'run') as command:
            with self.assertRaises(RuntimeError):self.w.prepare()
        command.assert_called_once()

if __name__=='__main__':unittest.main()
