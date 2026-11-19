"""Legacy upgrade snapshots must not retain local voice WAV blobs."""
import sqlite3
from contextlib import closing
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
                with closing(sqlite3.connect(path)) as db:
                    db.execute('CREATE TABLE profiles (id TEXT, name TEXT)')
                    db.execute('CREATE TABLE samples (id TEXT, audio BLOB)')
                    db.execute('INSERT INTO profiles VALUES (?, ?)', ('p1', 'Test'))
                    db.execute('INSERT INTO samples VALUES (?, ?)', ('s1', marker))
                    db.commit()
            self.assertEqual(state_backup.sanitize_retained_voice_snapshots(root), 1)
            with closing(sqlite3.connect(old / 'voice-profiles.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM samples').fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT name FROM profiles').fetchone()[0], 'Test')
            self.assertNotIn(marker, (old / 'voice-profiles.sqlite3').read_bytes())
            with closing(sqlite3.connect(root / 'voice-profiles.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT audio FROM samples').fetchone()[0], marker)

    def test_corrupt_backup_does_not_prevent_later_audio_erasure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            corrupt = root / 'upgrade-backups' / 'a-corrupt'
            healthy = root / 'upgrade-backups' / 'b-healthy'
            corrupt.mkdir(parents=True)
            healthy.mkdir()
            damaged = corrupt / 'voice-profiles.sqlite3'
            damaged.write_bytes(b'not a sqlite database')
            marker = b'RIFF-private-voice-audio'
            for folder in (root, healthy):
                with closing(sqlite3.connect(folder / 'voice-profiles.sqlite3')) as db:
                    db.execute('CREATE TABLE samples (id TEXT, audio BLOB)')
                    db.execute('INSERT INTO samples VALUES (?, ?)', ('s1', marker))
                    db.commit()
            with self.assertRaisesRegex(ValueError, 'sanitized 1 database.*1 database'):
                state_backup.sanitize_retained_voice_snapshots(root)
            self.assertEqual(damaged.read_bytes(), b'not a sqlite database')
            with closing(sqlite3.connect(healthy / 'voice-profiles.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM samples').fetchone()[0], 0)
            self.assertNotIn(marker, (healthy / 'voice-profiles.sqlite3').read_bytes())
            with closing(sqlite3.connect(root / 'voice-profiles.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT audio FROM samples').fetchone()[0], marker)
            self.assertEqual(list(healthy.glob('.voice-redaction-*')), [])
            self.assertEqual(list(corrupt.glob('.voice-redaction-*')), [])

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
