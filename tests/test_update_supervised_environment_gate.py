"""Verify the updater's exact supervised-install environment gate."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from declan.updates import updates


class SupervisedInstallEnvironmentTests(unittest.TestCase):
    def test_unset_empty_and_nonexact_values_reject_before_staging(self):
        for value in (None, "", "0", "true", "yes", " 1 ", "2"):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                settings = {} if value is None else {"DECLAN_UPDATE_SUPERVISED": value}
                with patch.dict(os.environ, settings, clear=True), patch.object(
                        updates, "mkdtemp") as stage, patch.object(
                        updates, "run") as command, patch.object(
                        updates, "trusted_releases") as trust, patch.object(
                        updates, "available_releases") as releases, patch.object(
                        updates, "release_source") as source:
                    updates.install(Path(directory), "v1.2.3", "a" * 40)
                stage.assert_not_called()
                command.assert_not_called()
                trust.assert_not_called()
                releases.assert_not_called()
                source.assert_not_called()

    def test_exact_one_passes_supervision_gate_before_release_validation(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
                os.environ, {"DECLAN_UPDATE_SUPERVISED": "1"}, clear=True), patch.object(
                updates, "release_source", return_value="github") as source, patch.object(
                updates, "mkdtemp") as stage, patch.object(updates, "run") as command:
            # A published release selection is required, so the install stops
            # after passing the supervision gate but before staging.
            updates.install(Path(directory), "v1.2.3", "a" * 40)
            source.assert_called_once_with()
            stage.assert_not_called()
            command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
