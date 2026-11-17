"""Runtime regression tests for Spotify preset environment configuration."""
import json
import os
import unittest
from unittest.mock import patch

import music


TRACK = "0123456789ABCDEFGHIJKL"
PLAYLIST = "ABCDEFGHIJKLMNOPQRSTUV"


class SpotifyPresetsEnvironmentDefaultsTests(unittest.TestCase):
    def selection(self, settings, title="evening mix"):
        with patch.dict(os.environ, settings, clear=True):
            return music.saved_spotify_selection(title, "")

    def test_unset_and_empty_settings_keep_builtin_presets(self):
        expected = music.saved_spotify_selection("coward of the county", "")
        self.assertIsNotNone(expected)
        for settings in ({}, {"DECLAN_SPOTIFY_PRESETS": ""}, {"DECLAN_SPOTIFY_PRESETS": "{}"}):
            with self.subTest(settings=settings), patch.dict(os.environ, settings, clear=True):
                self.assertEqual(music.saved_spotify_selection("coward of the county", ""), expected)

    def test_valid_override_uses_normalized_preset_name(self):
        settings = {"DECLAN_SPOTIFY_PRESETS": json.dumps({
            " Evening   Mix ": f"spotify:playlist:{PLAYLIST}"})}
        self.assertEqual(self.selection(settings),
                         (f"https://open.spotify.com/playlist/{PLAYLIST}", "playlist", "evening mix"))

    def test_malformed_non_object_and_invalid_references_are_ignored(self):
        for value in ("not json", "[]", "null",
                      json.dumps({"evening mix": "https://example.com/not-spotify"}),
                      json.dumps({"evening mix": 42})):
            with self.subTest(value=value):
                self.assertIsNone(self.selection({"DECLAN_SPOTIFY_PRESETS": value}))

    def test_valid_custom_preset_can_override_builtin(self):
        settings = {"DECLAN_SPOTIFY_PRESETS": json.dumps({
            "coward of the county": f"spotify:track:{TRACK}"})}
        self.assertEqual(self.selection(settings, "coward of the county"),
                         (f"https://open.spotify.com/track/{TRACK}", "track",
                          "coward of the county"))


if __name__ == "__main__":
    unittest.main()
