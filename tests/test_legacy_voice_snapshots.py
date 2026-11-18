"""Legacy upgrade snapshots must not retain local voice WAV blobs."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import state_backup


class LegacyVoiceSnapshotTests(unittest.TestCase):
    def test_sanitizes_legacy_snapshot_without_touching_live_database(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = root / 'upgrade-backups' / '20261101T000000Z-old'
            old.mkdir(parents=True)
            marker = b'RIFF' + b'private-audio' * 100
            for path in (root / 'voice-profiles.sqlite3', old / 'voice-profiles.sqlite3'):
                with sqlite3.connect(path) as db:
                    db.execute('CREATE TABLE profiles (id TEXT, name TEXT)')
                    db.execute('CREATE TABLE samples (id TEXT, audio BLOB)')
                    db.execute('INSERT INTO profiles VALUES (?, ?)', ('p1', 'Test'))
                    db.execute('INSERT INTO samples VALUES (?, ?)', ('s1', marker))
            self.assertEqual(state_backup.sanitize_retained_voice_snapshots(root), 1)
            with sqlite3.connect(old / 'voice-profiles.sqlite3') as db:
                self.assertEqual(db.execute('SELECT count(*) FROM samples').fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT name FROM profiles').fetchone()[0], 'Test')
            self.assertNotIn(marker, (old / 'voice-profiles.sqlite3').read_bytes())
            with sqlite3.connect(root / 'voice-profiles.sqlite3') as db:
                self.assertEqual(db.execute('SELECT audio FROM samples').fetchone()[0], marker)

    def test_rejects_symlinked_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            backups = root / 'upgrade-backups'
            backups.mkdir()
            (backups / 'linked').symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'Unexpected upgrade backup'):
                state_backup.sanitize_retained_voice_snapshots(root)


if __name__ == '__main__':
    unittest.main()
