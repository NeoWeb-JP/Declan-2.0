"""Linux deployment-style voice migration lifecycle tests using disposable SQLite files."""
import base64
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from check_voice_encryption import inspect, main as check_main
from migrate_voice_audio import migrate
from declan.voice.voice_audio_crypto import decrypt, encrypt


class VoiceMigrationLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / 'voice-profiles.sqlite3'
        self.key = base64.urlsafe_b64encode(b'a' * 32).decode()
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('CREATE TABLE samples (id TEXT PRIMARY KEY, audio BLOB NOT NULL)')
            db.commit()

    def samples(self):
        with closing(sqlite3.connect(self.database)) as db:
            return db.execute('SELECT id, audio FROM samples ORDER BY id').fetchall()

    def insert(self, sample_id, audio):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('INSERT INTO samples VALUES (?, ?)', (sample_id, audio))
            db.commit()

    def test_full_lifecycle_plaintext_mixed_migrate_verify_repeat(self):
        with patch.dict(os.environ, {'DECLAN_VOICE_AUDIO_KEY': self.key}):
            self.insert('first', b'RIFF-legacy-first')
            self.insert('second', encrypt(b'RIFF-existing-encrypted', 'second'))
            self.assertEqual(inspect(self.database), {'encrypted': 1, 'plaintext': 1})
            self.assertEqual(check_main(['--database', str(self.database)]), 2)
            original_encrypted = dict(self.samples())['second']
            self.assertEqual(migrate(self.database), 2)
            self.assertEqual(inspect(self.database), {'encrypted': 2, 'plaintext': 0})
            self.assertEqual(check_main(['--database', str(self.database)]), 0)
            rows = dict(self.samples())
            self.assertEqual(decrypt(rows['first'], 'first'), b'RIFF-legacy-first')
            self.assertEqual(decrypt(rows['second'], 'second'), b'RIFF-existing-encrypted')
            self.assertEqual(rows['second'], original_encrypted)
            self.assertNotIn(b'RIFF-legacy-first', self.database.read_bytes())
            self.assertEqual(migrate(self.database), 2)
            self.assertEqual(dict(self.samples()), rows)

    def test_wrong_key_blocks_check_and_migration_without_changes(self):
        with patch.dict(os.environ, {'DECLAN_VOICE_AUDIO_KEY': self.key}):
            self.insert('first', b'RIFF-legacy-first')
            self.insert('second', encrypt(b'private', 'second'))
        before = self.samples()
        other = base64.urlsafe_b64encode(b'b' * 32).decode()
        with patch.dict(os.environ, {'DECLAN_VOICE_AUDIO_KEY': other}):
            with self.assertRaises(Exception):
                inspect(self.database)
            with self.assertRaises(Exception):
                migrate(self.database)
        self.assertEqual(self.samples(), before)

    def test_empty_database_requires_key_but_needs_no_migration(self):
        with patch.dict(os.environ, {'DECLAN_VOICE_AUDIO_KEY': self.key}):
            self.assertEqual(inspect(self.database), {'encrypted': 0, 'plaintext': 0})
            self.assertEqual(migrate(self.database), 0)
            self.assertEqual(check_main(['--database', str(self.database)]), 0)
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                inspect(self.database)

    @unittest.skipUnless(os.name == 'posix', 'Symlink rejection is tested on Linux')
    def test_symlink_database_rejected_without_modification(self):
        link = self.database.parent / 'linked.sqlite3'
        link.symlink_to(self.database)
        with patch.dict(os.environ, {'DECLAN_VOICE_AUDIO_KEY': self.key}):
            with self.assertRaises(ValueError):
                inspect(link)
            with self.assertRaises(ValueError):
                migrate(link)
        self.assertEqual(self.samples(), [])


if __name__ == '__main__':
    unittest.main()
