"""Verify documented runtime paths and environment override precedence."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import approved_media_players
import spotify_playlists


class EnvironmentFilePathDefaultsTests(unittest.TestCase):
    def test_unset_paths_use_module_local_data_directories(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(approved_media_players.config_path(), approved_media_players.DEFAULT_PATH)
            self.assertEqual(spotify_playlists.catalogue_path(), spotify_playlists.DEFAULT_PATH)
            self.assertEqual(approved_media_players.config_path().name, "approved-media-players.json")
            self.assertEqual(spotify_playlists.catalogue_path().name, "spotify-playlists.json")

    def test_empty_path_overrides_still_use_safe_defaults(self):
        with patch.dict(os.environ, {
            "DECLAN_APPROVED_MEDIA_PLAYERS_FILE": "",
            "DECLAN_SPOTIFY_PLAYLISTS_FILE": "",
        }):
            self.assertEqual(approved_media_players.config_path(), approved_media_players.DEFAULT_PATH)
            self.assertEqual(spotify_playlists.catalogue_path(), spotify_playlists.DEFAULT_PATH)

    def test_nonempty_path_overrides_are_respected(self):
        with patch.dict(os.environ, {
            "DECLAN_APPROVED_MEDIA_PLAYERS_FILE": "/tmp/declan-approved.json",
            "DECLAN_SPOTIFY_PLAYLISTS_FILE": "/tmp/declan-spotify.json",
        }):
            self.assertEqual(approved_media_players.config_path(), Path("/tmp/declan-approved.json"))
            self.assertEqual(spotify_playlists.catalogue_path(), Path("/tmp/declan-spotify.json"))


if __name__ == "__main__":
    unittest.main()
