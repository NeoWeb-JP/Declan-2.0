"""Verify pinned updater allow-list environment and fail-closed validation."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import updates


class TrustedReleasesEnvironmentTests(unittest.TestCase):
    def test_relative_allowlist_path_is_rejected(self):
        with patch.dict(os.environ, {"DECLAN_TRUSTED_RELEASES": "trusted.json"}, clear=True):
            with self.assertRaisesRegex(ValueError, "root-owned"):
                updates.trusted_releases()

    @unittest.skipUnless(os.name == "posix", "Root-owned allow-list checks require POSIX")
    def test_unset_path_uses_fixed_administrator_location(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(
                updates.Path, "lstat", autospec=True, side_effect=FileNotFoundError) as inspect:
            with self.assertRaises(FileNotFoundError):
                updates.trusted_releases()
            self.assertEqual(str(inspect.call_args_list[0].args[0]), "/etc/declan/trusted-releases.json")

    @unittest.skipUnless(os.name == "posix", "Root-owned allow-list checks require POSIX")
    def test_non_root_owned_file_is_rejected_before_reading(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trusted.json"
            path.write_text("{}", encoding="utf-8")
            with patch.dict(os.environ, {"DECLAN_TRUSTED_RELEASES": str(path)}, clear=True), patch.object(
                    updates.Path, "read_text") as read:
                with self.assertRaisesRegex(ValueError, "root-owned"):
                    updates.trusted_releases()
                read.assert_not_called()

    @unittest.skipUnless(os.name == "posix", "Root-owned allow-list checks require POSIX")
    def test_invalid_allowlist_content_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trusted.json"
            # The ownership and permissions check is independently tested;
            # supply safe stat metadata to exercise content validation.
            import stat
            from types import SimpleNamespace
            safe = SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o600)
            for payload in ([], {"latest": "a" * 40}, {"v1.2.3": "invalid"},
                            {"v1.2.3": "A" * 40}):
                with self.subTest(payload=payload), patch.dict(
                        os.environ, {"DECLAN_TRUSTED_RELEASES": str(path)}, clear=True), patch.object(
                        updates.Path, "lstat", return_value=safe), patch.object(
                        updates.Path, "read_text", return_value=json.dumps(payload)):
                    with self.assertRaisesRegex(ValueError, "Invalid release allow-list"):
                        updates.trusted_releases()


if __name__ == "__main__":
    unittest.main()
