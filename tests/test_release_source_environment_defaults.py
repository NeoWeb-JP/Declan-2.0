"""Verify updater release-source environment defaults and strict validation."""
import os
import unittest
from unittest.mock import patch

import updates


class ReleaseSourceEnvironmentTests(unittest.TestCase):
    def source(self, settings):
        with patch.dict(os.environ, settings, clear=True):
            return updates.release_source()

    def test_unset_source_defaults_to_github(self):
        self.assertEqual(self.source({}), "github")

    def test_explicit_github_and_pinned_sources(self):
        for value in ("github", "pinned"):
            with self.subTest(value=value):
                self.assertEqual(self.source({"DECLAN_UPDATE_SOURCE": value}), value)

    def test_whitespace_is_trimmed(self):
        self.assertEqual(self.source({"DECLAN_UPDATE_SOURCE": "  pinned  "}), "pinned")

    def test_empty_unknown_and_case_variants_are_rejected(self):
        for value in ("", "   ", "GitHub", "PINNED", "local", "https://example.com"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "DECLAN_UPDATE_SOURCE"):
                    self.source({"DECLAN_UPDATE_SOURCE": value})


if __name__ == "__main__":
    unittest.main()
