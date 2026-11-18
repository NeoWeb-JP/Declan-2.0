"""Authenticated encryption for locally stored voice samples.

Key must be supplied independently of SQLite and upgrade snapshots via
DECLAN_VOICE_AUDIO_KEY (URL-safe base64 encoding of exactly 32 random bytes).
Never auto-generate a key: losing it would make existing samples unrecoverable.
"""
import base64
import binascii
import os
import secrets

MAGIC = b'DVAE1'


def _key():
    value = os.environ.get('DECLAN_VOICE_AUDIO_KEY', '')
    try:
        key = base64.b64decode(value, altchars=b'-_', validate=True)
    except (ValueError, binascii.Error) as error:
        raise RuntimeError('Configure a valid DECLAN_VOICE_AUDIO_KEY outside the data directory.') from error
    if len(key) != 32:
        raise RuntimeError('DECLAN_VOICE_AUDIO_KEY must encode exactly 32 random bytes.')
    return key


def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as error:
        raise RuntimeError('Install cryptography to use encrypted local voice samples.') from error
    return AESGCM(_key())


def encrypt(audio, sample_id):
    nonce = secrets.token_bytes(12)
    return MAGIC + nonce + _aesgcm().encrypt(nonce, audio, sample_id.encode('ascii'))


def decrypt(payload, sample_id):
    if not isinstance(payload, bytes) or not payload.startswith(MAGIC):
        raise RuntimeError('Unencrypted legacy sample found. Run the explicit voice encryption migration.')
    if len(payload) < len(MAGIC) + 12 + 16:
        raise ValueError('Encrypted sample is truncated.')
    nonce = payload[len(MAGIC):len(MAGIC) + 12]
    return _aesgcm().decrypt(nonce, payload[len(MAGIC) + 12:], sample_id.encode('ascii'))
