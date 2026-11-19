"""Verify release version environment validation and installed marker precedence."""
import os
import unittest
from unittest.mock import patch

from declan.updates import updates


class ConfiguredReleaseVersionTests(unittest.TestCase):
    def test_unset_blank_and_invalid_values_have_no_fallback(self):
        for value in (None, "", " ", "latest", "1.2", "1.2.3.4", "v1.2.3/evil", "v" + "1" * 41 + ".2.3"):
            with self.subTest(value=value):
                settings = {} if value is None else {"DECLAN_RELEASE_VERSION": value}
                with patch.dict(os.environ, settings, clear=True), patch.object(
                        updates, "installed_version", return_value=None) as installed:
                    self.assertIsNone(updates.configured_release_version())
                    installed.assert_called_once_with(None)

    def test_valid_values_are_trimmed_and_passed_as_fallback(self):
        for value, expected in (("  v1.2.3  ", "v1.2.3"), ("1.2.3", "1.2.3"),
                                ("1.2.3-rc.1", "1.2.3-rc.1"),
                                ("1.2.3+build.7", "1.2.3+build.7")):
            with self.subTest(value=value), patch.dict(
                    os.environ, {"DECLAN_RELEASE_VERSION": value}, clear=True), patch.object(
                    updates, "installed_version", return_value="v9.8.7") as installed:
                self.assertEqual(updates.configured_release_version(), "v9.8.7")
                installed.assert_called_once_with(expected)

    def test_installed_marker_absence_preserves_valid_fallback(self):
        with patch.dict(os.environ, {"DECLAN_RELEASE_VERSION": "v2.3.4"}, clear=True), patch.object(
                updates, "installed_version", side_effect=lambda fallback: fallback):
            self.assertEqual(updates.configured_release_version(), "v2.3.4")


if __name__ == "__main__":
    unittest.main()
