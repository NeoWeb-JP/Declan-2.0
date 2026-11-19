"""Authenticated local voice sample storage and legacy migration tests."""
import base64
from contextlib import closing
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from declan.voice.voice_audio_crypto import MAGIC, decrypt, encrypt, _key
from migrate_voice_audio import migrate


class VoiceEncryptionTests(unittest.TestCase):
    def test_key_has_no_default_and_rejects_blank_malformed_or_wrong_length_values(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                _key()
        for value in ('', ' ', 'not-base64!', base64.urlsafe_b64encode(b'k' * 31).decode(),
                      base64.urlsafe_b64encode(b'k' * 33).decode()):
            with self.subTest(value=value), patch.dict(os.environ, {'DECLAN_VOICE_AUDIO_KEY': value}):
                with self.assertRaises(RuntimeError):
                    _key()

    def test_encryption_roundtrip_and_wrong_identity(self):
        key = base64.urlsafe_b64encode(b'k' * 32).decode()
        with patch.dict(os.environ, {'DECLAN_VOICE_AUDIO_KEY': key}):
            ciphertext = encrypt(b'RIFF-private-test-audio', 'sample1')
            self.assertTrue(ciphertext.startswith(MAGIC))
            self.assertNotIn(b'RIFF-private-test-audio', ciphertext)
            self.assertEqual(decrypt(ciphertext, 'sample1'), b'RIFF-private-test-audio')
            with self.assertRaises(Exception):
                decrypt(ciphertext, 'sample2')

    def test_migrate_existing_sample_without_reencrypting_on_second_run(self):
        key = base64.urlsafe_b64encode(b'k' * 32).decode()
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'DECLAN_VOICE_AUDIO_KEY': key}):
            path = Path(temp) / 'voice-profiles.sqlite3'
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE samples (id TEXT PRIMARY KEY, audio BLOB)')
                db.execute('INSERT INTO samples VALUES (?, ?)', ('s1', b'RIFF-legacy-private'))
                db.commit()
            self.assertEqual(migrate(path), 1)
            with closing(sqlite3.connect(path)) as db:
                encrypted = db.execute('SELECT audio FROM samples').fetchone()[0]
            self.assertEqual(decrypt(encrypted, 's1'), b'RIFF-legacy-private')
            self.assertNotIn(b'RIFF-legacy-private', path.read_bytes())
            self.assertEqual(migrate(path), 1)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT audio FROM samples').fetchone()[0], encrypted)

    def test_wrong_key_does_not_migrate_other_plaintext_samples(self):
        first = base64.urlsafe_b64encode(b'k' * 32).decode()
        wrong = base64.urlsafe_b64encode(b'z' * 32).decode()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'voice-profiles.sqlite3'
            with patch.dict(os.environ, {'DECLAN_VOICE_AUDIO_KEY': first}):
                encrypted = encrypt(b'private', 's2')
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE samples (id TEXT PRIMARY KEY, audio BLOB)')
                db.executemany('INSERT INTO samples VALUES (?, ?)',
                               [('s1', b'RIFF-legacy-private'), ('s2', encrypted)])
                db.commit()
            with patch.dict(os.environ, {'DECLAN_VOICE_AUDIO_KEY': wrong}):
                with self.assertRaises(Exception):
                    migrate(path)
            with closing(sqlite3.connect(path)) as db:
                rows = db.execute('SELECT id, audio FROM samples ORDER BY id').fetchall()
            self.assertEqual(rows, [('s1', b'RIFF-legacy-private'), ('s2', encrypted)])

    def test_null_audio_rejected_without_modification(self):
        key = base64.urlsafe_b64encode(b'k' * 32).decode()
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'DECLAN_VOICE_AUDIO_KEY': key}):
            path = Path(temp) / 'voice-profiles.sqlite3'
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE samples (id TEXT PRIMARY KEY, audio BLOB)')
                db.executemany('INSERT INTO samples VALUES (?, ?)',
                               [('s1', b'RIFF-legacy-private'), ('s2', None)])
                db.commit()
            with self.assertRaisesRegex(ValueError, 'invalid audio'):
                migrate(path)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT audio FROM samples WHERE id = ?', ('s1',)).fetchone()[0],
                                 b'RIFF-legacy-private')


if __name__ == '__main__':
    unittest.main()
