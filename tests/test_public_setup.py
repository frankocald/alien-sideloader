import datetime as dt,hashlib,importlib.util,json,os,pathlib,plistlib,sys,tempfile,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))

def load():
    import setup_wizard
    return setup_wizard

class PublicSetupTests(unittest.TestCase):
    def test_no_personal_literals_or_private_artifacts(self):
        forbidden=['/Users/', 'discord-credentials.json\": {']
        for file in ROOT.rglob('*'):
            if not file.is_file() or 'tests' in file.parts or '__pycache__' in file.parts:continue
            self.assertNotIn(file.suffix,['.ipa','.mobileprovision','.p12','.key','.log'],str(file))
            if file.suffix in ['.py','.md','.json','.sh','.patch']:
                for value in forbidden:self.assertNotIn(value,file.read_text(),str(file))
    def test_discord_disabled_generates_private_runtime_with_eight_projects(self):
        wizard=load()
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)/'runtime'
            config=wizard.create_runtime(root,{'team':'TESTTEAM01','certificate':'1'*40,'device':'device-test','udid':'udid-test','bundle_id':'org.example.Apollo','group':wizard.suggest_group('org.example.Apollo')},discord=None)
            self.assertIsNotNone(config,'Setup must create a runtime and return its configuration')
            self.assertIsNone(config['discord'])
            self.assertFalse(root.stat().st_mode&0o077)
            self.assertFalse((root/'config.json').stat().st_mode&0o077)
            self.assertFalse((root/'discord-credentials.json').exists())
            for name,bundle in wizard.targets('org.example.Apollo').items():
                project=json.loads((root/'assets/ApolloSigning'/name/'Signing.xcodeproj/project.pbxproj').read_text())
                settings=[o['buildSettings'] for o in project['objects'].values() if 'buildSettings' in o]
                self.assertTrue(any(s.get('PRODUCT_BUNDLE_IDENTIFIER')==bundle for s in settings))
                self.assertTrue(all(s.get('DEVELOPMENT_TEAM')=='TESTTEAM01' for s in settings))
            state=json.loads((root/'state.json').read_text());self.assertEqual(state['installed_expiry'],0)
    def test_discord_token_only_in_owner_only_external_credential_file(self):
        wizard=load()
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)/'runtime';secret='example-secret-not-real'
            config=wizard.create_runtime(root,{'team':'TESTTEAM01','certificate':'1'*40,'device':'test','udid':'test','bundle_id':'org.example.Apollo','group':wizard.suggest_group('org.example.Apollo')},discord={'channel':'123','user':'456','token':secret})
            self.assertTrue((root/'config.json').exists(),'Setup must write configuration')
            self.assertNotIn(secret,(root/'config.json').read_text())
            self.assertEqual(json.loads((root/'discord-credentials.json').read_text())['token'],secret)
            self.assertFalse((root/'discord-credentials.json').stat().st_mode&0o077)
    def test_group_length_and_existing_runtime_are_rejected_without_mutation(self):
        wizard=load()
        with self.assertRaises(ValueError):wizard.validate_identity({'team':'TESTTEAM01','certificate':'1'*40,'device':'d','udid':'u','bundle_id':'org.example.Apollo','group':'group.too.long.'+'x'*50})
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);(root/'config.json').write_text('existing')
            with self.assertRaises(FileExistsError):wizard.create_runtime(root,{},None)
            self.assertEqual((root/'config.json').read_text(),'existing')
    def test_resume_reuses_only_complete_valid_matching_profile_set(self):
        wizard=load();certificate=b'test-certificate'
        identity={'team':'TESTTEAM01','certificate':hashlib.sha1(certificate).hexdigest(),'device':'test','udid':'phone','bundle_id':'org.example.Apollo','group':wizard.suggest_group('org.example.Apollo')}
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);profiles=root/'assets/apollo-signing-profiles';profiles.mkdir(parents=True)
            for name,bundle in wizard.targets(identity['bundle_id']).items():
                profile={'ExpirationDate':dt.datetime.utcnow()+dt.timedelta(days=7),'DeveloperCertificates':[certificate],'ProvisionedDevices':['phone'],'Entitlements':{'application-identifier':'TESTTEAM01.'+bundle,'com.apple.security.application-groups':[identity['group']] if name in wizard.GROUP_TARGETS else []}}
                (profiles/(name+'.mobileprovision')).write_bytes(plistlib.dumps(profile))
            with patch.object(wizard.subprocess,'check_output',side_effect=lambda command,**kw:pathlib.Path(command[-1]).read_bytes()):
                self.assertTrue(wizard.profiles_ready(root,identity),'Resume should reuse an already validated complete profile set')
                (profiles/'Apollo.mobileprovision').unlink()
                self.assertFalse(wizard.profiles_ready(root,identity))
    def test_launch_agent_does_not_contain_secret_and_runs_selected_runtime(self):
        wizard=load()
        data=wizard.launch_agent(pathlib.Path('/tmp/example runtime'))
        self.assertIn('StartInterval',data,'Setup must generate a periodic LaunchAgent')
        self.assertEqual(data['StartInterval'],10)
        self.assertEqual(data['ProgramArguments'][-2:],['--root',str(pathlib.Path('/tmp/example runtime').resolve())])
        self.assertNotIn('token',str(data))

if __name__=='__main__':unittest.main()
