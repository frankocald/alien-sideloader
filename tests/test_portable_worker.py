import importlib.util,json,pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('portable_job',ROOT/'scripts/apollo-sideload-job.py');j=importlib.util.module_from_spec(spec);spec.loader.exec_module(j)
SIGNING={'team':'TESTTEAM01','certificate':'1'*40,'device':'device-test','udid':'udid-test','bundle_id':'org.example.Apollo','group':'group.org.example.apollo'+'x'*7}
class PortableTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
  j.atomic_json(self.root/'config.json',{'assets':str(self.root),'discord':None,'signing':SIGNING})
  j.atomic_json(self.root/'state.json',{'last_success':0,'installed_expiry':0,'attempts':[],'pending':None,'outbox':[]})
 def tearDown(self):self.tmp.cleanup()
 def test_discord_off_does_not_queue_or_poll(self):
  w=j.Worker(self.root);w.new_cycle();w.alert('Failed during signing.');w.flush();w.poll()
  self.assertEqual(w.state['outbox'],[],'Discord-disabled runs must not leave an undeliverable queue')
  self.assertIsNone(w.state['pending']['message'])
 def test_worker_uses_configured_device_team_and_bundle_id(self):
  j.Worker(self.root)
  self.assertEqual(j.DEVICE,SIGNING['device'])
  self.assertEqual(j.TARGETS['Apollo'],SIGNING['bundle_id'])
  self.assertEqual(j.TEAM,SIGNING['team'])
if __name__=='__main__':unittest.main()
