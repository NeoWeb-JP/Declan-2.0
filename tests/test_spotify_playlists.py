"""Spotify catalogue is owned and persisted by Declan 2.0."""
import os
import tempfile
import unittest
from unittest.mock import patch

from declan.music import spotify_playlists as playlists


class SpotifyPlaylists(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {"DECLAN_SPOTIFY_PLAYLISTS_FILE": self.temp.name + "/catalogue.json"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.a = "spotify://playlist/" + "A" * 22
        self.b = "spotify://playlist/" + "B" * 22

    def test_add_remove_delete_and_restore(self):
        playlists.manage({"category": "country", "playlist": self.a, "operation": "add"})
        self.assertEqual(playlists.listing()["categories"]["country"]["playlists"], [self.a])
        playlists.manage({"category": "country", "playlist": self.a, "operation": "remove"})
        self.assertEqual(playlists.listing()["categories"]["country"]["playlists"], [])
        playlists.manage({"category": "country", "playlist": self.a, "operation": "delete"})
        playlists.refresh({"country": [self.a, self.b]})
        self.assertEqual(playlists.listing()["categories"]["country"]["playlists"], [self.b])
        playlists.manage({"category": "country", "playlist": self.a, "operation": "remove"})
        playlists.refresh({"country": [self.a, self.b]})
        self.assertIn(self.a, playlists.listing()["categories"]["country"]["playlists"])

    def test_limit_is_25_playlists_not_tracks(self):
        for i in range(25):
            playlists.manage({"category": "braai", "playlist": "spotify://playlist/" + f"{i:022d}", "operation": "add"})
        with self.assertRaises(ValueError):
            playlists.manage({"category": "braai", "playlist": self.a, "operation": "add"})
        self.assertEqual(len(playlists.listing()["categories"]["braai"]["playlists"]), 25)

    def test_refresh_preserves_pins_and_exclusions(self):
        playlists.manage({"category": "rock", "playlist": self.a, "operation": "add"})
        playlists.manage({"category": "rock", "playlist": self.b, "operation": "delete"})
        playlists.refresh({"rock": [self.a, self.b]})
        rock = playlists.listing()["categories"]["rock"]
        self.assertEqual(rock["playlists"], [self.a])
        self.assertEqual(rock["excluded"], [self.b])

    def test_refreshing_another_genre_keeps_previous_genre(self):
        playlists.refresh({"country": [self.a]}, {"country": {self.a: "Country A"}})
        playlists.refresh({"rock": [self.b]}, {"rock": {self.b: "Rock B"}})
        saved = playlists.listing()["categories"]
        self.assertEqual(saved["country"]["playlists"], [self.a])
        self.assertEqual(saved["country"]["titles"][self.a], "Country A")
        self.assertEqual(saved["rock"]["playlists"], [self.b])
        self.assertEqual(saved["rock"]["titles"][self.b], "Rock B")
        playlists.refresh({"country": [self.b]})
        saved = playlists.listing()["categories"]
        self.assertEqual(saved["rock"]["playlists"], [self.b])
        self.assertEqual(saved["country"]["playlists"], [self.b])

    def test_category_playback_uses_curated_playlist_without_search(self):
        from declan.music import music
        from pathlib import Path
        playlists.manage({"category": "country", "playlist": self.a, "operation": "add"})
        with patch.object(music, "PREFERENCES", Path(self.temp.name) / "preferences.sqlite3"), \
             patch.object(music, "spotify_search", side_effect=AssertionError("must use catalogue")):
            selected = music.search_media(None, None, "country music", "", "spotify")
        self.assertEqual(selected[0], "https://open.spotify.com/playlist/" + "A" * 22)
        self.assertEqual(selected[1], "playlist")

    def test_manual_category_discovery_uses_declan_spotify_search_and_preserves_pins(self):
        from declan.music import music
        playlists.manage({"category": "braai", "playlist": self.a, "operation": "add"})
        playlists.manage({"category": "braai", "playlist": self.b, "operation": "delete"})
        results = [
            ("https://open.spotify.com/playlist/" + "B" * 22, "playlist", "Blocked"),
            ("https://open.spotify.com/playlist/" + "C" * 22, "playlist", "Found"),
        ]
        with patch.object(music, "spotify_search", return_value=results) as search:
            data = playlists.discover(object(), "braai")
        self.assertEqual(len(search.call_args_list), 2)
        self.assertEqual(data["braai"]["playlists"],
                         [self.a, "spotify://playlist/" + "C" * 22])
        self.assertEqual(data["braai"]["excluded"], [self.b])

    def test_custom_genre_persists_and_refreshes_without_replacing_other_genres(self):
        from declan.music import music
        result = playlists.manage({"operation": "add_genre", "genre": "Blues & Soul"})
        self.assertIn("blues_soul", result["categories"])
        playlists.manage({"category": "blues_soul", "playlist": self.a, "operation": "add"})
        playlists.refresh({"country": [self.b]})
        self.assertEqual(playlists.load()["blues_soul"]["playlists"], [self.a])
        with patch.object(music, "spotify_search", return_value=[
            ("https://open.spotify.com/playlist/" + "C" * 22, "playlist", "Blues Playlist")
        ]) as search:
            playlists.discover(object(), "blues_soul")
        self.assertEqual(search.call_count, 2)
        self.assertEqual(playlists.load()["blues_soul"]["playlists"],
                         [self.a, "spotify://playlist/" + "C" * 22])
        self.assertEqual(playlists.load()["country"]["playlists"], [self.b])
        with self.assertRaises(ValueError):
            playlists.manage({"operation": "add_genre", "genre": "Blues & Soul"})

    def test_invalid_links_and_categories_rejected(self):
        for body in (
            {"category": "country", "playlist": "https://evil.test/playlist/" + "A" * 22, "operation": "add"},
            {"category": "other", "playlist": self.a, "operation": "add"},
            {"category": "rock", "playlist": self.a, "operation": "erase"},
        ):
            with self.assertRaises(ValueError):
                playlists.manage(body)


if __name__ == "__main__":
    unittest.main()
