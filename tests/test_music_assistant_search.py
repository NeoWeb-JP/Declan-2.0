"""DECLAN_MUSIC_ASSISTANT_SEARCH=1 hands Spotify requests to Music Assistant's own search."""
from unittest.mock import patch

import test_music as music_fixture
from declan.music import music
from result_pairs import pair_of


class MusicAssistantSearchTests(music_fixture.MusicFixture):
    def setUp(self):
        super().setUp()
        self.enterContext(patch.dict(music.os.environ, {
            "DECLAN_MUSIC_ASSISTANT_SEARCH": "1", "DECLAN_MUSIC_REPLY_FIRST": "0"}))
        self.spotify_requests = 0

    def open(self, request, timeout):
        if "spotify.com" in request.full_url:
            self.spotify_requests += 1
        return super().open(request, timeout)

    def play_from(self, phrase, origin):
        return pair_of(music.play_result)(music.parse(phrase), ("http://ha", {}, self),
                          lambda _: (list(self.players.values()), None), origin=origin)

    def play_media_calls(self):
        return [data for name, data in self.calls if name == "play_media"]

    def test_unqualified_request_goes_to_the_speaker_that_heard_it(self):
        self.players[self.bedroom].update(state="idle", attributes={})
        reply, outcome = self.play_from("play coldplay", self.kitchen)
        self.assertEqual(outcome, "confirmed", reply)
        self.assertEqual(self.play_media_calls(),
                         [{"entity_id": self.kitchen, "media_id": "coldplay", "enqueue": "play"}])
        self.assertEqual(self.spotify_requests, 0)
        self.assertEqual(self.searches, [])
        self.assertIn("in the kitchen", reply)

    def test_named_room_and_everywhere_go_to_that_player(self):
        self.players[self.bedroom].update(state="idle", attributes={})
        for phrase, entity in (("play rock in the bedroom", self.bedroom),
                               ("play rock everywhere", self.group)):
            with self.subTest(phrase=phrase):
                self.calls.clear()
                for row in self.players.values():
                    row.update(state="idle", attributes={})
                reply, outcome = self.play_from(phrase, self.kitchen)
                self.assertEqual(outcome, "confirmed", reply)
                self.assertEqual(self.play_media_calls()[0]["entity_id"], entity)
                self.assertEqual(self.play_media_calls()[0]["media_id"], "rock")
        self.assertEqual(self.spotify_requests, 0)

    def test_artist_and_playlist_hints_are_passed_to_music_assistant(self):
        self.players[self.bedroom].update(state="idle", attributes={})
        self.play_from("play yellow by coldplay in the kitchen", None)
        self.play_from("play country music in the bedroom", None)
        self.assertEqual(self.play_media_calls(), [
            {"entity_id": self.kitchen, "media_id": "yellow", "enqueue": "play",
             "media_type": "track", "artist": "coldplay"},
            {"entity_id": self.bedroom, "media_id": "country music", "enqueue": "play",
             "media_type": "playlist"},
        ])
        self.assertEqual(self.spotify_requests, 0)

    def test_works_without_spotify_credentials_and_bypasses_saved_links(self):
        self.players[self.bedroom].update(state="idle", attributes={})
        with patch.dict(music.os.environ, {"DECLAN_SPOTIFY_CLIENT_ID": "", "DECLAN_SPOTIFY_CLIENT_SECRET": "",
                                           "DECLAN_SPOTIFY_PRESETS": '{"bedtime songs": "https://open.spotify.com/playlist/0mQbGXAlmsI3T2Vyfa0IVd"}'}):
            reply, outcome = self.play_from("play bedtime songs in the kitchen", None)
        self.assertEqual(outcome, "confirmed", reply)
        self.assertEqual(self.play_media_calls()[0]["media_id"], "bedtime songs")
        self.assertEqual(self.spotify_requests, 0)

    def test_routine_playlists_are_sent_as_their_fixed_link(self):
        # A name search for "sexy time music" misses the "Sexy Time" playlist.
        self.players[self.bedroom].update(state="idle", attributes={})
        for phrase, uri in (
            ("play sexy time music in the bedroom", "https://open.spotify.com/playlist/0mQbGXAlmsI3T2Vyfa0IVd"),
            ("play romantic dinner music in the kitchen", "https://open.spotify.com/playlist/37i9dQZF1DXbm6HfkbMtFZ"),
        ):
            with self.subTest(phrase=phrase):
                self.calls.clear()
                for row in self.players.values():
                    row.update(state="idle", attributes={})
                reply, outcome = self.play_from(phrase, None)
                self.assertEqual(outcome, "confirmed", reply)
                call = self.play_media_calls()[0]
                self.assertEqual((call["media_id"], call["media_type"]), (uri, "playlist"))
        self.assertEqual(self.spotify_requests, 0)

    def test_playback_from_a_non_spotify_source_still_verifies(self):
        self.players[self.bedroom].update(state="idle", attributes={})

        def youtube(player, data):
            player.update(state="playing", attributes={"media_content_id": "ytmusic://track/abc", "media_title": "Yellow"})
        self.play_response = youtube
        reply, outcome = self.play_from("play yellow in the kitchen", None)
        self.assertEqual(outcome, "confirmed", reply)

    def test_no_playback_is_reported_unverified(self):
        self.players[self.bedroom].update(state="idle", attributes={})
        self.play_response = lambda player, data: None
        reply, outcome = self.play_from("play yellow in the kitchen", None)
        self.assertEqual(outcome, "unverified", reply)

    def test_moving_the_current_queue_is_unchanged(self):
        reply, outcome = self.play_from("play music in the kitchen", None)
        self.assertEqual(outcome, "confirmed", reply)
        self.assertEqual([name for name, _ in self.calls], ["transfer_queue"])

    def test_switching_the_flag_off_restores_declan_spotify_search(self):
        self.players[self.bedroom].update(state="idle", attributes={})
        with patch.dict(music.os.environ, {"DECLAN_MUSIC_ASSISTANT_SEARCH": "0"}):
            self.play_from("play yellow in the kitchen", None)
        self.assertGreater(self.spotify_requests, 0)
        self.assertTrue(self.play_media_calls()[0]["media_id"].startswith("https://open.spotify.com/"))

    def test_off_by_default_and_radio_is_unchanged(self):
        with patch.dict(music.os.environ, {"DECLAN_MUSIC_ASSISTANT_SEARCH": ""}):
            self.assertFalse(music.music_assistant_search_enabled())
        for value in ("1", "true", "Yes", " on "):
            with patch.dict(music.os.environ, {"DECLAN_MUSIC_ASSISTANT_SEARCH": value}):
                self.assertTrue(music.music_assistant_search_enabled())
        self.players[self.bedroom].update(state="idle", attributes={})
        self.search_results = {"radio": [{"name": "Jacaranda", "uri": "radio://jacaranda"}]}
        self.play_from("play jacaranda radio in the kitchen", None)
        self.assertEqual(self.play_media_calls()[0]["media_id"], "radio://jacaranda")


class UpstairsDownstairsParseTests(music_fixture.unittest.TestCase):
    def test_upstairs_and_downstairs_are_rooms_like_everywhere(self):
        self.assertEqual(music.parse("play rock upstairs"), ("upstairs", "rock", "spotify"))
        self.assertEqual(music.parse("play country music downstairs"), ("downstairs", "country music", "spotify"))
        self.assertEqual(music.parse("play rock upstairs on spotify"), ("upstairs", "rock", "spotify"))
        self.assertEqual(music.parse("play rock everywhere"), ("everywhere", "rock", "spotify"))
