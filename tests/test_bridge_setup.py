import pathlib,plistlib,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import setup_wizard as w
class BridgeSetupTests(unittest.TestCase):
 def test_usb_pairing_setup_uses_private_venv_and_selected_udid(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);config={'signing':{'udid':'test-phone'}}
   with patch.object(w.subprocess,'run') as run:
    result=w.create_usb_pairing(root,config,'/example/python3.12')
    self.assertIsNotNone(result,'Wizard must return its private USB pairing record path')
    self.assertEqual(result,root/'bridge/pairing.plist')
    self.assertEqual(run.call_args.args[0][-1],'test-phone')
    self.assertTrue(any('pymobiledevice3==11.12.4' in call.args[0] for call in run.call_args_list))
 def test_unpinned_or_wrong_device_record_rejected_before_build(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);record=root/'record.plist';record.write_bytes(plistlib.dumps({'peer_udid':'wrong-device'}));record.chmod(0o600)
   with patch.object(w.subprocess,'run') as run:
    with self.assertRaises(ValueError):w.import_pairing(root,{'signing':{'udid':'correct-device'}},record,'100.64.0.2')
    run.assert_not_called()
 def test_valid_private_record_is_copied_and_tailscale_address_required(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);record=root/'record.plist'
   record.write_bytes(plistlib.dumps({'peer_udid':'example-device','host_identifier':'example-host','host_alt_irk':bytes(16),'private_key':bytes(32),'public_key':bytes(32),'peer_public_key':bytes(32),'peer_identifier':'example-peer'}));record.chmod(0o600)
   config={'signing':{'udid':'example-device'}}
   with self.assertRaises(ValueError):w.import_pairing(root,config,record,'192.0.2.1')
   dest=w.import_pairing(root,config,record,'100.64.0.2')
   self.assertIsNotNone(dest,'Import must publish a pinned private record')
   self.assertFalse(dest.stat().st_mode&0o077)
   self.assertEqual(plistlib.loads(dest.read_bytes())['peer_udid'],'example-device')
if __name__=='__main__':unittest.main()
