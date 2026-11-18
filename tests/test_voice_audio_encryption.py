"""Authenticated local voice sample storage and legacy migration tests."""
import base64
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from voice_audio_crypto import MAGIC, decrypt, encrypt
from migrate_voice_audio import migrate


class VoiceEncryptionTests(unittest.TestCase):
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
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE samples (id TEXT PRIMARY KEY, audio BLOB)')
                db.execute('INSERT INTO samples VALUES (?, ?)', ('s1', b'RIFF-legacy-private'))
            self.assertEqual(migrate(path), 1)
            with sqlite3.connect(path) as db:
                encrypted = db.execute('SELECT audio FROM samples').fetchone()[0]
            self.assertEqual(decrypt(encrypted, 's1'), b'RIFF-legacy-private')
            self.assertNotIn(b'RIFF-legacy-private', path.read_bytes())
            self.assertEqual(migrate(path), 1)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT audio FROM samples').fetchone()[0], encrypted)


if __name__ == '__main__':
    unittest.main()
