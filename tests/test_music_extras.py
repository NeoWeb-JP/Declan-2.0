"""FUT-28: what's playing, play next, more like this, block an artist, sleep timer."""
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from declan.core.execution_results import Outcome
from declan.ha import ha_inventory
from declan.music import music, music_extras

KITCHEN = "media_player.kitchen_ma"
PLAYING: dict = {"entity_id": KITCHEN, "state": "playing", "declan_area": "Kitchen", "declan_music_assistant": True,
           "attributes": {"media_title": "Thunderstruck", "media_artist": "AC/DC",
                          "media_content_id": "spotify://track/" + "t" * 22, "volume_level": 0.5}}
SATELLITE = {"entity_id": "assist_satellite.kitchen", "state": "idle", "declan_area": "Kitchen", "declan_device": "dev-k"}


class Base(unittest.TestCase):
    def setUp(self):
        folder = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(music, "PREFERENCES", folder / "music-preferences.sqlite3"))
        self.calls: list = []
        self.enterContext(patch.object(music, "request", side_effect=self.fake_request))
        self.enterContext(patch.object(music, "music_players",
                                       side_effect=lambda inventory, origin=None: ({"kitchen": KITCHEN}, {
                                           row["entity_id"]: row for row in inventory
                                           if row["entity_id"].startswith("media_player.")})))
        self.inventory: list[dict] = [dict(PLAYING), SATELLITE]

    def fake_request(self, connection, path, data=None, *, timeout=None):
        self.calls.append((path, data))
        if path.startswith("/api/states/"):
            return {"attributes": {"volume_level": 0.5}}
        return {}

    def run_command(self, phrase, origin="dev-k", **kwargs):
        command = music_extras.parse(phrase)
        assert command is not None, phrase
        reader = lambda connection: ha_inventory.InventoryResult(tuple(self.inventory))
        return music_extras.result(command, ("http://ha", {}, None), reader, origin=origin, **kwargs)


class ParseTests(unittest.TestCase):
    def test_phrases(self):
        cases = {
            "what song is this": ("now_playing", None, None), "who sings this": ("now_playing", None, None),
            "what's playing in the kitchen": ("now_playing", "kitchen", None),
            "play bohemian rhapsody next": ("next", None, "bohemian rhapsody"),
            "queue thunderstruck by acdc": ("next", None, "thunderstruck by acdc"),
            "add jolene to the queue in the lounge": ("next", "lounge", "jolene"),
            "play something similar": ("similar", None, None), "more like this": ("similar", None, None),
            "don't play this artist again": ("block_artist", None, None),
            "stop the music in 30 minutes": ("sleep", None, 1800),
            "sleep timer 45 minutes in the bedroom": ("sleep", "bedroom", 2700),
            "cancel the sleep timer": ("sleep_cancel", None, None),
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(music_extras.parse(phrase), expected)

    def test_other_phrases_are_left_alone(self):
        for phrase in ("play jazz", "what is this", "what's the time", "play this next", "stop the music", "who is this"):
            with self.subTest(phrase=phrase):
                self.assertIsNone(music_extras.parse(phrase))


class ResultTests(Base):
    def test_now_playing(self):
        result = self.run_command("what song is this")
        self.assertEqual((result.reply, result.outcome), ("This is Thunderstruck by AC/DC.", Outcome.CHAT_ANSWER))
        self.inventory[0] = {**PLAYING, "state": "idle"}
        self.assertEqual(self.run_command("what song is this", origin=None).reply, "Nothing's playing, boet.")

    def test_play_next_searches_then_queues(self):
        with patch.object(music, "music_assistant_search_enabled", return_value=False), \
                patch.object(music, "search_media", return_value=("https://open.spotify.com/track/x", "track", "Jolene")):
            result = self.run_command("play jolene next")
        self.assertEqual((result.reply, result.outcome), ("Jolene is up next.", Outcome.REQUESTED))
        self.assertEqual(self.calls[-1], ("/api/services/music_assistant/play_media",
                                          {"entity_id": KITCHEN, "media_id": "https://open.spotify.com/track/x",
                                           "enqueue": "next"}))
        with patch.object(music, "music_assistant_search_enabled", return_value=True):
            self.run_command("queue jolene by dolly parton")
        self.assertEqual(self.calls[-1][1]["media_id"], "jolene by dolly parton")

    def test_similar_uses_radio_mode_from_the_current_track(self):
        result = self.run_command("play something similar")
        self.assertEqual(result.outcome, Outcome.REQUESTED)
        self.assertEqual(self.calls[-1][1], {"entity_id": KITCHEN, "media_id": PLAYING["attributes"]["media_content_id"],
                                             "media_type": "track", "radio_mode": True, "enqueue": "replace"})

    def test_block_artist_skips_now_and_later_and_can_be_undone(self):
        result = self.run_command("don't play this artist again")
        self.assertIn("Blocked AC/DC", result.reply)
        self.assertEqual(self.calls[-1][0], "/api/services/media_player/media_next_track")
        self.assertTrue(music_extras.is_blocked({"media_artist": "AC/DC, Brian Johnson"}))
        self.assertFalse(music_extras.is_blocked({"media_artist": "Dolly Parton"}))
        self.calls.clear()
        with patch.object(music.RUNTIME, "allow_blacklist_skip", return_value=True):
            music.skip_blocked_tracks(("http://ha", {}, None), lambda connection: ha_inventory.InventoryResult(tuple(self.inventory)))
        self.assertEqual(self.calls, [("/api/services/media_player/media_next_track", {"entity_id": KITCHEN})])
        self.assertTrue(music_extras.unblock_artist("AC/DC"))
        self.assertFalse(music_extras.is_blocked({"media_artist": "AC/DC"}))

    def test_sleep_timer_fades_stops_restores_and_can_be_cancelled(self):
        timers = []

        def factory(delay, function, args):
            timer = SimpleNamespace(delay=delay, start=lambda: None, cancel=lambda: None, daemon=False,
                                    run=lambda: function(*args))
            timers.append(timer)
            return timer
        result = self.run_command("stop the music in 30 minutes", timer_factory=factory)
        self.assertEqual(result.reply, "Sleep timer set. The music here fades out in 30 minutes.")
        self.assertEqual(timers[0].delay, 1800 - music_extras.FADE_SECONDS)
        with patch.object(music_extras, "FADE_SECONDS", 0):
            timers[0].run()
        volumes = [data["volume_level"] for path, data in self.calls if path.endswith("/volume_set")]
        self.assertEqual(volumes[:-1], sorted(volumes[:-1], reverse=True))
        self.assertEqual(volumes[-2:], [0.0, 0.5])  # faded to nothing, then put back for next time
        self.assertIn(("/api/services/media_player/media_stop", {"entity_id": KITCHEN}), self.calls)
        self.run_command("sleep timer 20 minutes", timer_factory=factory)
        self.assertEqual(self.run_command("cancel the sleep timer").reply, "Sleep timer cancelled. The music stays on.")
        self.assertEqual(self.run_command("cancel the sleep timer").reply, "There's no sleep timer running.")
        self.assertEqual(self.run_command("sleep timer 10 seconds").outcome, Outcome.UNRESOLVED)

    def test_new_music_cancels_a_sleep_timer(self):
        event = threading.Event()
        music_extras._SLEEPERS[KITCHEN] = (SimpleNamespace(cancel=lambda: None), event)  # type: ignore[assignment]
        self.assertTrue(music_extras.cancel_sleep(KITCHEN))
        self.assertTrue(event.is_set())

    def test_failures_are_reported_honestly(self):
        from email.message import Message
        from urllib.error import HTTPError
        self.enterContext(patch.object(music, "request", side_effect=HTTPError("u", 500, "x", Message(), None)))
        self.assertEqual(self.run_command("play something similar").outcome, Outcome.UNAVAILABLE)
        self.assertEqual(music_extras.result(("now_playing", None, None), None, None).outcome, Outcome.NOT_CONFIGURED)


class SettingsTests(Base):
    def test_blocked_artists_are_listed_and_unblocked(self):
        from declan.http import settings_read_routes
        from declan.music import media_settings_post
        self.run_command("don't play this artist again")
        handler = SimpleNamespace(path="/api/settings/music", sent=[])
        handler.send_json = lambda status, payload: handler.sent.append((status, payload))
        settings_read_routes.dispatch(handler, voicepipeline=None, voice_profiles=None, diagnostics=None,
                                      history=None, ai_budget=None, ai_settings=None, ai_credentials=None,
                                      spotify_playlists=None)
        self.assertEqual(handler.sent[-1][1]["blocked_artists"], ["AC/DC"])
        media_settings_post.dispatch(handler, {"unblock_artist": "AC/DC"}, music=music, spotify_playlists=None,
                                     playlist_handler=None, opener_factory=None)
        self.assertEqual(handler.sent[-1], (200, {"unblocked": True}))


if __name__ == "__main__":
    unittest.main()
