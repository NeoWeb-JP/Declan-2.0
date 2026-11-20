"""#760: voice-sample keys can be rotated without re-encrypting everything at once."""
import base64
from contextlib import closing
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.exceptions import InvalidTag

from check_voice_encryption import inspect
from declan.voice.voice_audio_crypto import (
    MAGIC, MAGIC_V2, _aesgcm, decrypt, encrypt, is_encrypted, key_id_of,
)
from migrate_voice_audio import migrate

OLD = base64.urlsafe_b64encode(b'o' * 32).decode()
NEW = base64.urlsafe_b64encode(b'n' * 32).decode()


def env(**values):
    names = {'key': 'DECLAN_VOICE_AUDIO_KEY', 'key_id': 'DECLAN_VOICE_AUDIO_KEY_ID',
             'previous': 'DECLAN_VOICE_AUDIO_PREVIOUS_KEYS'}
    return patch.dict(os.environ, {names[k]: v for k, v in values.items()}, clear=True)


class FormatTests(unittest.TestCase):
    def test_without_key_id_new_samples_keep_the_original_format(self):
        with env(key=OLD):
            payload = encrypt(b'audio', 's1')
            self.assertTrue(payload.startswith(MAGIC))
            self.assertIsNone(key_id_of(payload))
            self.assertEqual(decrypt(payload, 's1'), b'audio')

    def test_key_id_records_the_key_and_binds_it_to_the_ciphertext(self):
        with env(key=NEW, key_id='2026-11'):
            payload = encrypt(b'audio', 's1')
            self.assertTrue(payload.startswith(MAGIC_V2))
            self.assertEqual(key_id_of(payload), '2026-11')
            self.assertTrue(is_encrypted(payload))
            self.assertEqual(decrypt(payload, 's1'), b'audio')
            with self.assertRaises(InvalidTag):
                decrypt(payload, 's2')
            # Swapping the recorded key ID for another configured key fails authentication.
        with env(key=NEW, key_id='2026-11', previous=f'other:{NEW}'):
            forged = payload.replace(b'\x072026-11', b'\x05other', 1)
            with self.assertRaises(InvalidTag):
                decrypt(forged, 's1')

    def test_truncated_and_plaintext_payloads_fail_closed(self):
        with env(key=NEW, key_id='k2'):
            payload = encrypt(b'audio', 's1')
            with self.assertRaises(ValueError):
                decrypt(payload[:12], 's1')
            with self.assertRaises(RuntimeError):
                decrypt(b'RIFF-plaintext', 's1')
            self.assertFalse(is_encrypted(b'RIFF-plaintext'))


class RotationTests(unittest.TestCase):
    def test_old_samples_stay_readable_through_previous_keys(self):
        with env(key=OLD):
            legacy = encrypt(b'legacy', 's1')
        with env(key=OLD, key_id='k1'):
            tagged = encrypt(b'tagged', 's2')
        with env(key=NEW, key_id='k2', previous=f'k1:{OLD}'):
            self.assertEqual(decrypt(legacy, 's1'), b'legacy')
            self.assertEqual(decrypt(tagged, 's2'), b'tagged')
            self.assertEqual(key_id_of(encrypt(b'new', 's3')), 'k2')

    def test_missing_previous_key_is_a_clear_error_not_a_silent_failure(self):
        with env(key=OLD, key_id='k1'):
            tagged = encrypt(b'tagged', 's1')
        with env(key=NEW, key_id='k2'):
            with self.assertRaisesRegex(RuntimeError, '"k1"'):
                decrypt(tagged, 's1')
        with env(key=OLD):
            legacy = encrypt(b'legacy', 's1')
        with env(key=NEW, key_id='k2'):
            with self.assertRaises(InvalidTag):
                decrypt(legacy, 's1')

    def test_invalid_rotation_configuration_is_rejected_by_preflight(self):
        for values in (
            dict(key=NEW, key_id='has space'),
            dict(key=NEW, key_id='x' * 33),
            dict(key=NEW, key_id='k2', previous='k1'),
            dict(key=NEW, key_id='k2', previous=f'k1:{OLD},k1:{OLD}'),
            dict(key=NEW, key_id='k2', previous='k1:not-base64!'),
            dict(key=NEW, key_id='k2', previous=f'k2:{OLD}'),
        ):
            with self.subTest(values=values), env(**values), self.assertRaises(RuntimeError):
                _aesgcm()

    def test_rewrap_moves_every_sample_to_the_current_key_atomically(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'voice-profiles.sqlite3'
            with env(key=OLD):
                legacy = encrypt(b'legacy', 's1')
            with env(key=OLD, key_id='k1'):
                tagged = encrypt(b'tagged', 's2')
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE samples (id TEXT PRIMARY KEY, audio BLOB)')
                db.executemany('INSERT INTO samples VALUES (?, ?)',
                               [('s1', legacy), ('s2', tagged), ('s3', b'RIFF-plain')])
                db.commit()
            with env(key=NEW, key_id='k2', previous=f'k1:{OLD}'):
                # Without --rewrap only plaintext is encrypted; DVAE2 rows are not double-encrypted.
                self.assertEqual(migrate(path), 3)
                with closing(sqlite3.connect(path)) as db:
                    rows = dict(db.execute('SELECT id, audio FROM samples'))
                self.assertEqual(rows['s2'], tagged)
                self.assertEqual(key_id_of(rows['s3']), 'k2')
                self.assertEqual(inspect(path), {'encrypted': 3, 'plaintext': 0})
                self.assertEqual(migrate(path, rewrap=True), 3)
                with closing(sqlite3.connect(path)) as db:
                    rows = dict(db.execute('SELECT id, audio FROM samples'))
                self.assertEqual({key_id_of(v) for v in rows.values()}, {'k2'})
            with env(key=NEW, key_id='k2'):
                # The old key can now be removed.
                self.assertEqual(inspect(path), {'encrypted': 3, 'plaintext': 0})
                self.assertEqual(decrypt(rows['s1'], 's1'), b'legacy')

    def test_rewrap_with_an_unknown_key_changes_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'voice-profiles.sqlite3'
            with env(key=OLD, key_id='k1'):
                tagged = encrypt(b'tagged', 's1')
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE samples (id TEXT PRIMARY KEY, audio BLOB)')
                db.executemany('INSERT INTO samples VALUES (?, ?)', [('s1', tagged), ('s2', b'RIFF')])
                db.commit()
            with env(key=NEW, key_id='k2'), self.assertRaises(RuntimeError):
                migrate(path, rewrap=True)
            with closing(sqlite3.connect(path)) as db:
                rows = dict(db.execute('SELECT id, audio FROM samples'))
            self.assertEqual(rows, {'s1': tagged, 's2': b'RIFF'})


if __name__ == '__main__':
    unittest.main()
