"""Modules moved into declan/ must still use the repository's .data directory and root."""
import importlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (module, attribute, expected path relative to the repository root)
EXPECTED = [
    ("declan.updates.updates", "APP", "."),
    ("declan.timers.timers", "DATABASE", ".data/timers.sqlite3"),
    ("declan.music.music", "SPOTIFY_SETTINGS", ".data/spotify-settings.json"),
    ("declan.music.approved_media_players", "DEFAULT_PATH", ".data/approved-media-players.json"),
    ("declan.music.spotify_playlists", "DEFAULT_PATH", ".data/spotify-playlists.json"),
]


class PackageDataPathTests(unittest.TestCase):
    def test_moved_modules_still_point_at_repository_root(self):
        for module, attribute, relative in EXPECTED:
            with self.subTest(module=module, attribute=attribute):
                value = getattr(importlib.import_module(module), attribute)
                self.assertEqual(Path(value).resolve(), (ROOT / relative).resolve())

    def test_every_package_directory_is_a_package(self):
        for directory in (ROOT / "declan").iterdir():
            if directory.is_dir() and directory.name != "__pycache__":
                self.assertTrue((directory / "__init__.py").is_file(), directory)


if __name__ == "__main__":
    unittest.main()
