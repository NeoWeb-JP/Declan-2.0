"""Authenticated encryption for locally stored voice samples.

Key must be supplied independently of SQLite and upgrade snapshots via
DECLAN_VOICE_AUDIO_KEY (URL-safe base64 encoding of exactly 32 random bytes).
Never auto-generate a key: losing it would make existing samples unrecoverable.

Key rotation (#760):
- DECLAN_VOICE_AUDIO_KEY_ID (optional) names the current key. When it is set, new
  samples use the DVAE2 format, which records the key ID in the header and binds
  it to the ciphertext. When it is unset, new samples keep the original DVAE1
  format, so an older release can still read them.
- DECLAN_VOICE_AUDIO_PREVIOUS_KEYS (optional) lists retired keys as
  ``id:base64key`` entries separated by commas. They are only used to decrypt.
- ``python -m migrate_voice_audio --rewrap`` re-encrypts every sample under the
  current key; afterwards the previous keys can be removed.
"""
import base64
import binascii
import os
import re
import secrets

MAGIC = b'DVAE1'
MAGIC_V2 = b'DVAE2'
_NONCE = 12
_TAG = 16
_KEY_ID = re.compile(r'[A-Za-z0-9_.-]{1,32}')


def _decode(value, name):
    try:
        key = base64.b64decode(value, altchars=b'-_', validate=True)
    except (ValueError, binascii.Error) as error:
        raise RuntimeError(f'Configure a valid {name} outside the data directory.') from error
    if len(key) != 32:
        raise RuntimeError(f'{name} must encode exactly 32 random bytes.')
    return key


def _key():
    return _decode(os.environ.get('DECLAN_VOICE_AUDIO_KEY', ''), 'DECLAN_VOICE_AUDIO_KEY')


def current_key_id():
    """Return the configured current key ID, or None for the original DVAE1 format."""
    value = os.environ.get('DECLAN_VOICE_AUDIO_KEY_ID', '').strip()
    if not value:
        return None
    if not _KEY_ID.fullmatch(value):
        raise RuntimeError('DECLAN_VOICE_AUDIO_KEY_ID must be 1-32 letters, digits, dots, dashes or underscores.')
    return value


def previous_keys():
    """Return retired decryption-only keys as an ordered {key_id: key} mapping."""
    keys = {}
    raw = os.environ.get('DECLAN_VOICE_AUDIO_PREVIOUS_KEYS', '').strip()
    for entry in filter(None, (part.strip() for part in raw.split(','))):
        key_id, separator, value = entry.partition(':')
        if not separator or not _KEY_ID.fullmatch(key_id) or key_id in keys:
            raise RuntimeError('DECLAN_VOICE_AUDIO_PREVIOUS_KEYS must be unique id:base64key entries.')
        keys[key_id] = _decode(value, 'DECLAN_VOICE_AUDIO_PREVIOUS_KEYS')
    if current_key_id() in keys:
        raise RuntimeError('The current key ID must not also be listed as a previous key.')
    return keys


def _cipher(key):
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as error:
        raise RuntimeError('Install cryptography to use encrypted local voice samples.') from error
    return AESGCM(key)


def _aesgcm():
    """Cipher for the current key. The updater preflight calls this to validate configuration."""
    current_key_id()
    previous_keys()
    return _cipher(_key())


def is_encrypted(payload):
    return isinstance(payload, bytes) and payload.startswith((MAGIC, MAGIC_V2))


def key_id_of(payload):
    """Key ID recorded in a DVAE2 payload; None for DVAE1 (key not recorded)."""
    if isinstance(payload, bytes) and payload.startswith(MAGIC_V2) and len(payload) > len(MAGIC_V2):
        length = payload[len(MAGIC_V2)]
        return payload[len(MAGIC_V2) + 1:len(MAGIC_V2) + 1 + length].decode('ascii', 'replace')
    return None


def _v2_aad(sample_id, key_id):
    return sample_id.encode('ascii') + b'\x00' + key_id.encode('ascii')


def encrypt(audio, sample_id):
    nonce = secrets.token_bytes(_NONCE)
    key_id = current_key_id()
    cipher = _aesgcm()
    if key_id is None:
        return MAGIC + nonce + cipher.encrypt(nonce, audio, sample_id.encode('ascii'))
    header = MAGIC_V2 + bytes([len(key_id)]) + key_id.encode('ascii')
    return header + nonce + cipher.encrypt(nonce, audio, _v2_aad(sample_id, key_id))


def decrypt(payload, sample_id):
    if not is_encrypted(payload):
        raise RuntimeError('Unencrypted legacy sample found. Run the explicit voice encryption migration.')
    if payload.startswith(MAGIC_V2):
        return _decrypt_v2(payload, sample_id)
    if len(payload) < len(MAGIC) + _NONCE + _TAG:
        raise ValueError('Encrypted sample is truncated.')
    nonce = payload[len(MAGIC):len(MAGIC) + _NONCE]
    body = payload[len(MAGIC) + _NONCE:]
    aad = sample_id.encode('ascii')
    # DVAE1 does not record its key: try the current key, then retired keys.
    from cryptography.exceptions import InvalidTag
    try:
        return _cipher(_key()).decrypt(nonce, body, aad)
    except InvalidTag:
        for key in previous_keys().values():
            try:
                return _cipher(key).decrypt(nonce, body, aad)
            except InvalidTag:
                continue
        raise


def _decrypt_v2(payload, sample_id):
    start = len(MAGIC_V2) + 1
    if len(payload) < start:
        raise ValueError('Encrypted sample is truncated.')
    length = payload[len(MAGIC_V2)]
    key_id = payload[start:start + length].decode('ascii', 'replace')
    if not _KEY_ID.fullmatch(key_id) or len(payload) < start + length + _NONCE + _TAG:
        raise ValueError('Encrypted sample header is invalid or truncated.')
    if key_id == current_key_id():
        key = _key()
    else:
        key = previous_keys().get(key_id)
        if key is None:
            raise RuntimeError(f'Voice sample was encrypted with key "{key_id}", which is not configured.')
    nonce = payload[start + length:start + length + _NONCE]
    return _cipher(key).decrypt(nonce, payload[start + length + _NONCE:], _v2_aad(sample_id, key_id))
