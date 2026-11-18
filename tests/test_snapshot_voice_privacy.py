"""Privacy regression: new upgrade snapshots never retain local WAV sample blobs."""
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

import state_backup


class SnapshotVoicePrivacyTests(unittest.TestCase):
    def test_snapshot_redacts_audio_but_preserves_profile_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            database = directory / 'voice-profiles.sqlite3'
            marker = b'RIFF' + b'secret-voice-recording' * 100
            with closing(sqlite3.connect(database)) as db:
                db.execute('CREATE TABLE profiles (id TEXT PRIMARY KEY, name TEXT, consent_at REAL)')
                db.execute('CREATE TABLE samples (id TEXT PRIMARY KEY, profile TEXT, audio BLOB)')
                db.execute('INSERT INTO profiles VALUES (?, ?, ?)', ('p1', 'Test Person', 1.0))
                db.execute('INSERT INTO samples VALUES (?, ?, ?)', ('s1', 'p1', marker))
                db.commit()
            name = state_backup.snapshot(directory)
            backup = directory / 'upgrade-backups' / name / 'voice-profiles.sqlite3'
            with closing(sqlite3.connect(backup)) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM samples').fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT name FROM profiles').fetchone()[0], 'Test Person')
            self.assertNotIn(marker, backup.read_bytes())
            with closing(sqlite3.connect(database)) as db:
                self.assertEqual(db.execute('SELECT audio FROM samples').fetchone()[0], marker)


if __name__ == '__main__':
    unittest.main()
