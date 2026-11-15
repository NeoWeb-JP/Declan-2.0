"""Spotify catalogue is owned and persisted by Declan 2.0."""
import os
import tempfile
import unittest
from unittest.mock import patch

import spotify_playlists as playlists


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
