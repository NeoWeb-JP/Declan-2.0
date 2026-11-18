"""Standalone snapshot cleanup command tests."""
import contextlib
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path

import sanitize_voice_backups


class VoiceCleanupCommandTests(unittest.TestCase):
    def test_explicit_command_cleans_old_backup_without_creating_new_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            old = data / 'upgrade-backups' / 'old'
            old.mkdir(parents=True)
            database = old / 'voice-profiles.sqlite3'
            with sqlite3.connect(database) as db:
                db.execute('CREATE TABLE samples (id TEXT, audio BLOB)')
                db.execute('INSERT INTO samples VALUES (?, ?)', ('s1', b'RIFF-secret-audio'))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(sanitize_voice_backups.main(['--data-dir', str(data)]), 0)
            self.assertIn('Sanitized 1', output.getvalue())
            with sqlite3.connect(database) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM samples').fetchone()[0], 0)
            self.assertEqual(list((data / 'upgrade-backups').iterdir()), [old])

    def test_invalid_data_directory_fails_without_creating_it(self):
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / 'missing'
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    sanitize_voice_backups.main(['--data-dir', str(missing)])
            self.assertNotEqual(raised.exception.code, 0)
            self.assertFalse(missing.exists())


if __name__ == '__main__':
    unittest.main()
