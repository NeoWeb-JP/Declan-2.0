"""Verify updater installation-root environment defaults and layout guards."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import updates


class UpdateRootEnvironmentTests(unittest.TestCase):
    def test_unset_and_blank_root_disable_updater(self):
        for settings in ({}, {"DECLAN_UPDATE_ROOT": ""}):
            with self.subTest(settings=settings), patch.dict(os.environ, settings, clear=True):
                self.assertIsNone(updates.layout())

    def test_relative_root_is_rejected(self):
        with patch.dict(os.environ, {"DECLAN_UPDATE_ROOT": "releases"}, clear=True):
            self.assertIsNone(updates.layout())

    @unittest.skipUnless(os.name == "posix", "Updater layout is supported only on POSIX")
    def test_valid_absolute_root_requires_current_symlink_and_releases_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "application"
            app.mkdir()
            releases = root / "releases"
            releases.mkdir()
            (root / "current").symlink_to(app, target_is_directory=True)
            with patch.dict(os.environ, {"DECLAN_UPDATE_ROOT": str(root)}, clear=True), patch.object(
                    updates, "APP", app):
                self.assertEqual(updates.layout(), root)
                (root / "current").unlink()
                self.assertIsNone(updates.layout())

    @unittest.skipUnless(os.name == "posix", "Updater layout is supported only on POSIX")
    def test_current_symlink_must_point_to_running_application(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "application"
            other = root / "other"
            app.mkdir()
            other.mkdir()
            (root / "releases").mkdir()
            (root / "current").symlink_to(other, target_is_directory=True)
            with patch.dict(os.environ, {"DECLAN_UPDATE_ROOT": str(root)}, clear=True), patch.object(
                    updates, "APP", app):
                self.assertIsNone(updates.layout())

    @unittest.skipUnless(os.name == "posix", "Updater layout is supported only on POSIX")
    def test_missing_releases_directory_disables_updater(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "application"
            app.mkdir()
            (root / "current").symlink_to(app, target_is_directory=True)
            with patch.dict(os.environ, {"DECLAN_UPDATE_ROOT": str(root)}, clear=True), patch.object(
                    updates, "APP", app):
                self.assertIsNone(updates.layout())


if __name__ == "__main__":
    unittest.main()
