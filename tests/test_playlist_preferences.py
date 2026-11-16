"""Playlist preference, dislike and playback count regression tests."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import music
import spotify_playlists

A = "spotify://playlist/" + "A" * 22
B = "spotify://playlist/" + "B" * 22


class PlaylistPreferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"DECLAN_SPOTIFY_PLAYLISTS_FILE": str(Path(self.temp.name) / "playlists.json")})
        self.environment.start()
        self.original_preferences = music.PREFERENCES
        music.PREFERENCES = Path(self.temp.name) / "preferences.sqlite3"

    def tearDown(self):
        music.PREFERENCES = self.original_preferences
        self.environment.stop()
        self.temp.cleanup()

    def test_love_and_dislike_commands(self):
        self.assertEqual(music.parse_feedback("i love this playlist")[0], "i love this playlist")
        self.assertEqual(music.parse_feedback("i don't like this song")[0], "i don't like this song")
        self.assertEqual(music.parse_feedback("never play this playlist again")[0], "never play this playlist again")

    def test_favourite_is_weighted_and_restorable(self):
        spotify_playlists.refresh({"country": [A, B]})
        spotify_playlists.manage({"category": "country", "playlist": A, "operation": "favourite"})
        self.assertIn(A, spotify_playlists.listing()["preferences"]["favourites"])
        spotify_playlists.manage({"category": "country", "playlist": A, "operation": "unfavourite"})
        self.assertNotIn(A, spotify_playlists.listing()["preferences"]["favourites"])

    def test_dislike_blocks_all_genres_and_refresh(self):
        spotify_playlists.refresh({"country": [A, B], "rock": [A]})
        spotify_playlists.manage({"category": "country", "playlist": A, "operation": "dislike"})
        spotify_playlists.refresh({"country": [A, B], "rock": [A]})
        catalogue = spotify_playlists.listing()
        self.assertNotIn(A, catalogue["categories"]["country"]["playlists"])
        self.assertNotIn(A, catalogue["categories"]["rock"]["playlists"])
        self.assertIn(A, catalogue["preferences"]["disliked_playlists"])
        spotify_playlists.manage({"category": "country", "playlist": A, "operation": "restore"})
        spotify_playlists.refresh({"country": [A], "rock": [A]})
        self.assertIn(A, spotify_playlists.listing()["categories"]["rock"]["playlists"])

    def test_disliked_songs_can_be_restored_separately(self):
        song = "spotify://track/" + "C" * 22
        with music.preference_db() as db:
            db.execute("INSERT INTO preferences(uri, weight) VALUES (?, 0)", (song,))
        self.assertIn(song, spotify_playlists.listing()["preferences"]["disliked_songs"])
        spotify_playlists.manage({"category": "disliked_songs", "playlist": song, "operation": "restore"})
        self.assertNotIn(song, spotify_playlists.listing()["preferences"]["disliked_songs"])

    def test_global_disliked_playlist_restore(self):
        spotify_playlists.refresh({"country": [A], "rock": [A]})
        spotify_playlists.manage({"category": "country", "playlist": A, "operation": "dislike"})
        spotify_playlists.manage({"category": "disliked_playlists", "playlist": A, "operation": "restore"})
        self.assertNotIn(A, spotify_playlists.listing()["preferences"]["disliked_playlists"])

    def test_play_counts_are_read_from_database(self):
        with music.preference_db() as db:
            db.execute("INSERT INTO playlist_play_counts(uri, plays) VALUES (?, ?)", (A, 7))
        self.assertEqual(spotify_playlists.listing()["preferences"]["play_counts"][A], 7)


if __name__ == "__main__":
    unittest.main()
