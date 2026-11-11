import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase, skipUnless
from unittest.mock import patch

import updates


class UpdateTests(TestCase):
    def setUp(self):
        self.enterContext(patch.object(updates, "trusted_releases", return_value={
            tag: "a" * 40 for tag in ("0.1.0", "0.2.0", "0.10.0", "v0.1.1")}))
        self.enterContext(patch.dict(os.environ, {"DECLAN_UPDATE_SUPERVISED": "1", "DECLAN_UPDATE_SOURCE": "pinned"}))

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

    def test_unapproved_release_never_clones_or_executes_code(self):
        with patch.object(updates, 'run') as run, patch.object(updates, '_job', {}):
            updates.install(Path('/unused'), '9.9.9', 'a' * 40)
            run.assert_not_called()
            self.assertEqual(updates.status()['state'], 'failed')

    def test_missing_supervisor_never_clones(self):
        with patch.dict(os.environ, {'DECLAN_UPDATE_SUPERVISED': ''}), patch.object(updates, 'run') as run:
            updates.install(Path('/unused'), '0.2.0', 'a' * 40)
            run.assert_not_called()

    @skipUnless(os.name == 'posix', 'Linux deployment uses symbolic links')
    def test_unapproved_commit_never_runs_release_or_pip(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'releases').mkdir()
            with patch.object(updates, 'run', return_value='b' * 40) as run:
                updates.install(root, '0.2.0', 'b' * 40)
            self.assertFalse(any('venv' in call.args or 'pip' in call.args or 'server.py' in call.args
                                 for call in run.call_args_list))
            self.assertEqual(list((root / 'releases').iterdir()), [])

    @skipUnless(os.name == 'posix', 'Linux deployment uses symbolic links')
    def test_installs_only_hashed_wheels_and_failed_pip_does_not_activate(self):
        import subprocess
        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / 'baseline'
            app.mkdir()
            (root / 'releases').mkdir()
            (root / 'current').symlink_to(app)
            def command(*args, **kwargs):
                if args[:2] == ('git', 'clone'):
                    (Path(args[-1]) / 'requirements-web-voice.txt').write_text('bad dependency')
                if 'pip' in args:
                    self.assertIn('--require-hashes', args)
                    self.assertIn('--only-binary=:all:', args)
                    raise subprocess.CalledProcessError(1, args)
                return 'a' * 40
            with patch.object(updates, 'APP', app), patch.object(updates, 'run', side_effect=command):
                updates.install(root, '0.2.0', 'a' * 40)
            self.assertEqual((root / 'current').resolve(), app)
            self.assertEqual(list((root / 'releases').iterdir()), [])


class ReleaseTrustTests(TestCase):
    def test_trust_file_rejects_writable_paths_symlinks_and_bad_pins(self):
        from types import SimpleNamespace
        import stat
        path = Path('/etc/declan/trusted-releases.json').absolute()
        with patch.object(updates, 'Path', return_value=path), patch.object(updates, 'os',
                SimpleNamespace(name='posix', environ={})), patch.object(type(path), 'lstat') as info, patch.object(
                type(path), 'read_text', return_value='{"0.2.0":"' + 'a' * 40 + '"}') as read:
            info.return_value = SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o644)
            self.assertEqual(updates.trusted_releases(), {'0.2.0': 'a' * 40})
            for uid, mode in ((1, 0o644), (0, 0o666), (0, stat.S_IFLNK | 0o777)):
                info.return_value = SimpleNamespace(st_uid=uid, st_mode=mode)
                with self.assertRaises(ValueError):
                    updates.trusted_releases()
            info.return_value = SimpleNamespace(st_uid=0, st_mode=0o644)
            for content in ('[]', '{"bad":"sha"}', '{"0.2.0":null}'):
                read.return_value = content
                with self.assertRaises(ValueError):
                    updates.trusted_releases()
