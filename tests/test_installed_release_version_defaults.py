"""Verify installed release marker precedence and fallback behaviour."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from declan.updates import updates


class InstalledReleaseVersionTests(unittest.TestCase):
    def test_missing_marker_preserves_configured_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(updates, "APP", Path(directory)):
                self.assertEqual(updates.installed_version("v1.2.3"), "v1.2.3")
                self.assertIsNone(updates.installed_version(None))

    def test_valid_marker_overrides_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".declan-release").write_text("  v2.3.4  ", encoding="ascii")
            with patch.object(updates, "APP", root):
                self.assertEqual(updates.installed_version("v1.2.3"), "v2.3.4")

    def test_invalid_marker_preserves_fallback(self):
        for value in ("", "latest", "v1.2", "v1.2.3 extra", "v999999999.1.2"):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / ".declan-release").write_text(value, encoding="ascii")
                with patch.object(updates, "APP", root):
                    self.assertEqual(updates.installed_version("v1.2.3"), "v1.2.3")

    def test_non_ascii_marker_preserves_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".declan-release").write_bytes(b"\xff\xfe")
            with patch.object(updates, "APP", root):
                self.assertEqual(updates.installed_version("v1.2.3"), "v1.2.3")


if __name__ == "__main__":
    unittest.main()
