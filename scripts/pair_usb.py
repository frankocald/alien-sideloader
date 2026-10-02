# SPDX-License-Identifier: GPL-3.0-only
# Optional USB pairing helpers: see licenses/GPL-3.0.txt and THIRD_PARTY_NOTICES.md.
"""Capture the device signing identity only through the existing trusted USB connection."""
import asyncio, inspect, os, plistlib, subprocess, sys, textwrap
from pathlib import Path
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pymobiledevice3 import usbmux
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.remote import tunnel_service as ts
from pymobiledevice3.exceptions import RemotePairingCompletedError

os.umask(0o077)
record_path=Path(sys.argv[1]).resolve()
from pairing_identity import fresh_record, verify_peer
if not record_path.exists():
 if len(sys.argv)!=3:raise SystemExit('Usage: pair_usb.py <record.plist> <trusted iPhone UDID>')
 record_path.parent.mkdir(parents=True,exist_ok=True)
 record=fresh_record(sys.argv[2])
 fd=os.open(record_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'wb') as f:f.write(plistlib.dumps(record))
record=plistlib.loads(record_path.read_bytes())
phone=record['peer_udid']
if record_path.stat().st_mode & 0o077: raise SystemExit('Pairing record must be owner-only')
info=ts.PairableHostInfo(name='iOS OTA',model=subprocess.check_output(['sysctl','-n','hw.model'],text=True).strip(),identifier=record['host_identifier'],alt_irk=record['host_alt_irk'])
source=textwrap.dedent(inspect.getsource(ts.RemotePairingProtocol._save_pair_record_on_peer))
replacements={
 'self.ed25519_private_key = Ed25519PrivateKey.generate()':"self.ed25519_private_key = Ed25519PrivateKey.from_private_bytes(self.bridge_existing_record['private_key'])",
 '"altIRK": b"\\xe9\\xe8-\\xc0jIykVoT\\x00\\x19\\xb1\\xc7{",':'"altIRK": self.bridge_host_info.alt_irk,',
 '"model": "computer-model",':'"model": self.bridge_host_info.model,',
 '"name": platform.node(),':'"name": self.bridge_host_info.name,',
}
for old,new in replacements.items():
 if source.count(old)!=1: raise RuntimeError('Upstream method changed; refusing to patch')
 source=source.replace(old,new)
namespace=dict(vars(ts));exec(source,namespace)
base_save=namespace['_save_pair_record_on_peer']
class PinUSBService(ts.RemotePairingLockdownService):
 @property
 def pair_record_path(self): return record_path
 @property
 def pair_record(self): return None  # Explicit trusted USB re-setup, using the existing host identity.
 async def _save_pair_record_on_peer(self):
  result=await base_save(self)
  decoded=self.decode_tlv(result)
  key=decoded[ts.PairingDataComponentType.PUBLIC_KEY]
  identifier=decoded[ts.PairingDataComponentType.IDENTIFIER]
  signature=decoded[ts.PairingDataComponentType.SIGNATURE]
  identifier,key=verify_peer(self.encryption_key,identifier,key,signature)
  self.bridge_peer_key=key;self.bridge_peer_identifier=identifier
  return result
 def save_pair_record(self):
  data=dict(record)
  data.update(peer_public_key=self.bridge_peer_key,peer_identifier=self.bridge_peer_identifier,remote_unlock_host_key=self.remote_unlock_host_key)
  stage=record_path.with_name(record_path.name+'.pin-stage')
  fd=os.open(stage,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,'wb') as f: f.write(plistlib.dumps(data));f.flush();os.fsync(f.fileno())
  os.replace(stage,record_path)
async def main():
 async with await usbmux.create_mux() as mux: usb_record=await mux.get_pair_record(phone)
 async with await create_using_usbmux(serial=phone,connection_type='USB',autopair=False,pair_record=usb_record) as lockdown:
  if not lockdown.paired: raise RuntimeError('Trusted USB pairing is unavailable')
  service=await PinUSBService.create(lockdown)
  service.bridge_host_info=info;service.bridge_existing_record=record;service.identifier=info.identifier
  try:
   try: await service.connect(autopair=True)
   except RemotePairingCompletedError: pass
  finally: await service.close()
 saved=plistlib.loads(record_path.read_bytes())
 if len(saved.get('peer_public_key',b''))!=32: raise RuntimeError('Device identity was not saved')
 print('Verified phone signing identity saved owner-only.',flush=True)
asyncio.run(asyncio.wait_for(main(),120))
