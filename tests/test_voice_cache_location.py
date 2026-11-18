"""Existing voice cache data stays accessible across the Jarvis-to-Declan rename."""

import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


PATH = (Path(__file__).resolve().parents[1] /
        "custom_components/declan_two/voice_cache_location.py")
SPEC = importlib.util.spec_from_file_location("voice_cache_location_test", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class VoiceCacheLocationTests(unittest.TestCase):
    def test_new_install_uses_declan_directory(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            selected = MODULE.select_cache_directory(lambda name: root / name)
            self.assertEqual(selected, root / "declan_voice_cache")
            self.assertFalse(selected.exists())

    def test_existing_legacy_cache_is_reused_without_copy_or_delete(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "jarvis_voice_cache"
            legacy.mkdir()
            (legacy / "existing.mp3").write_bytes(b"previously generated")
            selected = MODULE.select_cache_directory(lambda name: root / name)
            self.assertEqual(selected, legacy)
            self.assertEqual((selected / "existing.mp3").read_bytes(),
                             b"previously generated")
            self.assertFalse((root / "declan_voice_cache").exists())

    def test_legacy_cache_is_preferred_when_both_directories_exist(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "jarvis_voice_cache").mkdir()
            (root / "declan_voice_cache").mkdir()
            selected = MODULE.select_cache_directory(lambda name: root / name)
            self.assertEqual(selected, root / "jarvis_voice_cache")


if __name__ == "__main__":
    unittest.main()
