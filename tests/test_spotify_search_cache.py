"""Resolved Spotify track/artist searches are remembered; playlist picks never are."""
import os
from unittest.mock import patch

import music
from test_music import MusicFixture

PHRASE = "play hello by adele in the kitchen"


class SearchCacheTests(MusicFixture):
    def setUp(self):
        super().setUp()
        for row in self.players.values():
            row.update(state="idle", attributes={})

    def play_idle(self, phrase=PHRASE):
        for row in self.players.values():
            row.update(state="idle", attributes={})
        return self.play(phrase)

    def cached(self):
        with music.preference_db() as db:
            return db.execute("SELECT key, uri FROM search_cache").fetchall()

    def test_second_identical_request_skips_spotify_and_plays_the_same_item(self):
        self.assertEqual(self.play_idle()[1], "confirmed")
        first_media = self.calls[-1][1]["media_id"]
        self.assertEqual(len(self.searches), 1)
        self.assertEqual(self.play_idle()[1], "confirmed")
        self.assertEqual(len(self.searches), 1)
        self.assertEqual(self.calls[-1][1]["media_id"], first_media)

    def test_key_ignores_case_and_spacing(self):
        self.assertEqual(music.search_cache_key("  Hello  ", "ADELE"), music.search_cache_key("hello", "adele"))

    def test_different_artist_is_a_different_entry(self):
        self.play_idle()
        self.play_idle("play hello by lionel richie in the kitchen")
        self.assertEqual(len(self.searches), 2)
        self.assertEqual(len(self.cached()), 2)

    def test_market_is_part_of_the_key(self):
        self.play_idle()
        with patch.dict(os.environ, {"DECLAN_SPOTIFY_MARKET": "ZA"}):
            self.play_idle()
        self.assertEqual(len(self.searches), 2)

    def test_playlist_picks_are_never_cached(self):
        self.search_results = {"playlists": [{"name": "Country Music", "id": "A" * 22}]}
        self.play_idle("play country music in the kitchen")
        self.play_idle("play country music in the kitchen")
        self.assertEqual(len(self.searches), 2)
        self.assertEqual(self.cached(), [])

    def test_entries_expire(self):
        self.play_idle()
        with patch.object(music, "time", return_value=music.time() + 8 * 86400):
            self.play_idle()
        self.assertEqual(len(self.searches), 2)

    def test_disliked_item_is_dropped_not_replayed(self):
        self.play_idle()
        (_, uri), = self.cached()
        with music.preference_db() as db:
            db.execute("INSERT OR REPLACE INTO preferences(uri, weight) VALUES (?, 0)", (music.media_key(uri),))
        reply, outcome = self.play_idle()
        self.assertEqual(len(self.searches), 2)  # looked up again, not served from memory
        self.assertNotEqual(outcome, "confirmed", reply)
        self.assertEqual(self.cached(), [])

    def test_zero_days_disables_the_cache(self):
        with patch.dict(os.environ, {"DECLAN_SPOTIFY_SEARCH_CACHE_DAYS": "0"}):
            self.play_idle()
            self.play_idle()
        self.assertEqual(len(self.searches), 2)
        self.assertEqual(self.cached(), [])

    def test_ttl_parsing(self):
        for value, days in (("", 7), ("abc", 7), ("2", 2), ("-3", 0), ("9999", 365), ("0", 0)):
            with patch.dict(os.environ, {"DECLAN_SPOTIFY_SEARCH_CACHE_DAYS": value}):
                self.assertEqual(music.search_cache_ttl(), days * 86400, value)
