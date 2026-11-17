"""Verify updater release trust-source environment defaults."""
import os
import unittest
from unittest.mock import patch

import updates
from updates import release_source


class UpdateSourceEnvironmentTests(unittest.TestCase):
    def test_unset_source_defaults_to_github(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(release_source(), "github")

    def test_supported_sources_are_accepted(self):
        for value in ("github", "pinned", " github "):
            with self.subTest(value=value):
                with patch.dict(os.environ, {"DECLAN_UPDATE_SOURCE": value}):
                    self.assertEqual(release_source(), value.strip())

    def test_empty_and_unknown_sources_are_rejected(self):
        for value in ("", "other", "Github", "pinned,github"):
            with self.subTest(value=value):
                with patch.dict(os.environ, {"DECLAN_UPDATE_SOURCE": value}):
                    with self.assertRaises(ValueError):
                        release_source()


    def test_unset_supervisor_fails_closed_before_execution(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(updates, "run") as run, patch.object(updates, "_job", {"state": "idle"}):
                updates.install(None, "0.1.0", "a" * 40)
                run.assert_not_called()
                self.assertEqual(updates.status()["state"], "failed")

    def test_invalid_supervisor_values_never_execute_commands(self):
        for value in ("", "true", "0", "yes"):
            with self.subTest(value=value):
                with patch.dict(os.environ, {"DECLAN_UPDATE_SUPERVISED": value}):
                    with patch.object(updates, "run") as run, patch.object(updates, "_job", {"state": "idle"}):
                        updates.install(None, "0.1.0", "a" * 40)
                        run.assert_not_called()
                        self.assertEqual(updates.status()["state"], "failed")

if __name__ == "__main__":
    unittest.main()
