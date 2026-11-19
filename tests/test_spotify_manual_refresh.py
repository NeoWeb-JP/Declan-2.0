"""Manual Spotify category refresh starts real discovery without blocking HA."""
from email.message import Message
import os
import tempfile
import time
import unittest
from urllib.error import HTTPError
from unittest.mock import patch
from declan.music import spotify_playlists as sp
from declan.music.playlist_refresh_state import PlaylistRefreshState


class PlaylistRefreshTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"DECLAN_SPOTIFY_PLAYLISTS_FILE": temp.name + "/playlists.json"})
        env.start()
        self.addCleanup(env.stop)
        self.enterContext(patch.object(sp, "RUNTIME", PlaylistRefreshState()))

    def wait(self):
        for _ in range(100):
            if not sp.listing()["refresh"]["running"]:
                return
            time.sleep(.01)
        self.fail("Spotify refresh did not complete")

    def test_manual_refresh_populates_selected_category(self):
        from declan.music import music
        result = [("https://open.spotify.com/playlist/" + "A"*22, "playlist", "Country mix")]
        with patch.object(music, "spotify_search", return_value=result) as search:
            started = sp.start_refresh("country", lambda: object())
            self.assertTrue(started["refresh"]["running"] or started["refresh"]["completed"])
            self.wait()
        self.assertEqual(len(search.call_args_list), 2)
        self.assertEqual(sp.listing()["categories"]["country"]["playlists"], ["spotify://playlist/" + "A"*22])
        self.assertEqual(sp.listing()["categories"]["rock"]["playlists"], [])
        self.assertEqual(sp.listing()["categories"]["country"]["titles"]["spotify://playlist/" + "A"*22], "Country mix")
        self.assertIsNone(sp.listing()["refresh"]["error"])

    def test_failure_retains_existing_playlists(self):
        from declan.music import music
        uri = "spotify://playlist/" + "B"*22
        sp.manage({"category":"country","playlist":uri,"operation":"add"})
        with patch.object(music, "spotify_search", side_effect=TimeoutError):
            sp.start_refresh("country", lambda: object())
            self.wait()
        self.assertIn(uri, sp.listing()["categories"]["country"]["playlists"])
        self.assertIn("TimeoutError", sp.listing()["refresh"]["error"])

    def test_spotify_forbidden_reports_status_and_keeps_catalogue(self):
        from declan.music import music
        uri = "spotify://playlist/" + "B"*22
        sp.manage({"category":"country","playlist":uri,"operation":"add"})
        with patch.object(music, "spotify_search", side_effect=HTTPError(
                "https://api.spotify.com/v1/search", 403, "Forbidden", Message(), None)):
            sp.start_refresh("country", lambda: object())
            self.wait()
        self.assertIn("403", sp.listing()["refresh"]["error"])
        self.assertIn("API access", sp.listing()["refresh"]["error"])
        self.assertIn(uri, sp.listing()["categories"]["country"]["playlists"])

    def test_invalid_category_is_rejected(self):
        with self.assertRaises(ValueError):
            sp.start_refresh("invalid", lambda: object())


if __name__ == "__main__":
    unittest.main()
