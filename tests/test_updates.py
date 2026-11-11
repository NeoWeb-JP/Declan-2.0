import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase, skipUnless
from unittest.mock import patch

import updates


class UpdateTests(TestCase):
    def test_lists_only_version_tags_in_version_order(self):
        refs = "\n".join(f"{'a' * 40}\trefs/tags/{tag}" for tag in ("0.2.0", "0.10.0", "v0.1.1", "test"))
        with patch.object(updates, "layout", return_value=Path("/test")), patch.object(updates, "run", return_value=refs), patch.object(updates, "_tags", {}):
            self.assertEqual(updates.check(), ["0.10.0", "0.2.0", "v0.1.1"])
            with self.assertRaises(ValueError):
                updates.queue("test", "0.2.0")

    @skipUnless(os.name == "posix", "Linux deployment uses symbolic links")
    def test_stages_release_and_preserves_state_before_restart(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "baseline"
            (app / ".data").mkdir(parents=True)
            (root / "releases").mkdir()
            (root / "current").symlink_to(app)
            restart = Event()
            with patch.dict(os.environ, {"DECLAN_UPDATE_ROOT": directory}), patch.object(updates, "APP", app), patch.object(
                updates, "RESTART", restart,
            ), patch.object(updates, "_job", {"state": "idle"}), patch.object(updates, "run", return_value="a" * 40):
                updates.install(root, "0.1.0", "b" * 40)
                self.assertEqual((root / "current").resolve(), app)
                self.assertFalse(restart.is_set())
                self.assertFalse(list((root / "releases").iterdir()))
                updates.install(root, "0.1.0", "a" * 40)
                selected = (root / "current").resolve()
                self.assertEqual((selected / ".data").resolve(), app / ".data")
                self.assertEqual((selected / ".declan-release").read_text().strip(), "0.1.0")
                self.assertEqual((root / "previous").resolve(), app)
                self.assertTrue(restart.is_set())

    @skipUnless(os.name == "posix", "Linux deployment uses symbolic links")
    def test_bad_state_never_activates_release_or_leaves_update_stuck(self):
        import sqlite3
        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / 'baseline'
            (app / '.data').mkdir(parents=True)
            (root / 'releases').mkdir()
            (root / 'current').symlink_to(app)
            restart = Event()
            job = {'state': 'installing'}
            with patch.dict(os.environ, {'DECLAN_UPDATE_ROOT': directory}), patch.object(updates, 'APP', app), patch.object(
                updates, 'RESTART', restart
            ), patch.object(updates, '_job', job), patch.object(updates, 'run', return_value='a' * 40), patch.object(
                updates.state_backup, 'snapshot', side_effect=sqlite3.DatabaseError('bad store')
            ):
                updates.install(root, '0.2.0', 'a' * 40)
                self.assertEqual(job['state'], 'failed')
                self.assertEqual((root / 'current').resolve(), app)
                self.assertFalse(restart.is_set())
                self.assertEqual(list((root / 'releases').iterdir()), [])
