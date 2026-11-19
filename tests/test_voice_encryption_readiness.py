"""Read-only local voice encryption readiness regression tests."""
import base64
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from check_voice_encryption import inspect, main
from declan.voice.voice_audio_crypto import encrypt


class VoiceReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'voice-profiles.sqlite3'
        self.key = base64.urlsafe_b64encode(b'k' * 32).decode()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE TABLE samples (id TEXT PRIMARY KEY, audio BLOB NOT NULL)')
            db.commit()

    def insert(self, sample_id, audio):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('INSERT INTO samples VALUES (?, ?)', (sample_id, audio))
            db.commit()

    def test_encrypted_samples_pass_without_modification(self):
        with patch.dict(os.environ, {'DECLAN_VOICE_AUDIO_KEY': self.key}):
            self.insert('s1', encrypt(b'private', 's1'))
            before = self.path.read_bytes()
            self.assertEqual(inspect(self.path), {'encrypted': 1, 'plaintext': 0})
            self.assertEqual(self.path.read_bytes(), before)

    def test_plaintext_is_reported_and_blocks_readiness(self):
        self.insert('s1', b'RIFF-legacy')
        with patch.dict(os.environ, {'DECLAN_VOICE_AUDIO_KEY': self.key}):
            self.assertEqual(inspect(self.path), {'encrypted': 0, 'plaintext': 1})
            self.assertEqual(main(['--database', str(self.path)]), 2)

    def test_wrong_key_fails_closed(self):
        with patch.dict(os.environ, {'DECLAN_VOICE_AUDIO_KEY': self.key}):
            self.insert('s1', encrypt(b'private', 's1'))
        other = base64.urlsafe_b64encode(b'z' * 32).decode()
        with patch.dict(os.environ, {'DECLAN_VOICE_AUDIO_KEY': other}):
            with self.assertRaises(Exception):
                inspect(self.path)

    def test_missing_key_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                inspect(self.path)


if __name__ == '__main__':
    unittest.main()
