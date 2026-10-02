# SPDX-License-Identifier: GPL-3.0-only
# Optional USB pairing helpers: see licenses/GPL-3.0.txt and THIRD_PARTY_NOTICES.md.
"""Authenticated USB pairing identity primitives; optional cryptography dependency."""
import os,uuid

def fresh_record(udid):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    key=Ed25519PrivateKey.generate()
    return {'peer_udid':udid,'host_identifier':str(uuid.uuid4()).upper(),'host_alt_irk':os.urandom(16),
            'private_key':key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption()),
            'public_key':key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)}

def verify_peer(encryption_key,identifier,key,signature):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    if len(key)!=32 or not identifier:raise ValueError('Invalid phone identity')
    accessory=HKDF(algorithm=hashes.SHA512(),length=32,salt=b'Pair-Setup-Accessory-Sign-Salt',info=b'Pair-Setup-Accessory-Sign-Info').derive(encryption_key)
    Ed25519PublicKey.from_public_bytes(key).verify(signature,accessory+identifier+key)
    return identifier.decode('utf-8'),key
