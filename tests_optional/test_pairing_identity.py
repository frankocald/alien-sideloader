import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import pairing_identity as p
class PairingTests(unittest.TestCase):
 def test_new_host_identity_is_unique_and_corresponds_to_its_public_key(self):
  first=p.fresh_record('test-phone');second=p.fresh_record('test-phone')
  self.assertIn('private_key',first,'Bootstrap must generate an independent host signing identity')
  self.assertNotEqual(first['private_key'],second['private_key'])
  key=Ed25519PrivateKey.from_private_bytes(first['private_key'])
  self.assertEqual(first['public_key'],key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw))
  self.assertEqual(len(first['host_alt_irk']),16);self.assertEqual(first['peer_udid'],'test-phone')
 def test_peer_pin_requires_authenticated_accessory_signature(self):
  private=Ed25519PrivateKey.generate();public=private.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
  secret=b'session-secret';identifier=b'test-peer'
  accessory=HKDF(algorithm=hashes.SHA512(),length=32,salt=b'Pair-Setup-Accessory-Sign-Salt',info=b'Pair-Setup-Accessory-Sign-Info').derive(secret)
  signature=private.sign(accessory+identifier+public)
  self.assertEqual(p.verify_peer(secret,identifier,public,signature),('test-peer',public))
  with self.assertRaises(Exception):p.verify_peer(secret,b'different-peer',public,signature)
if __name__=='__main__':unittest.main()
