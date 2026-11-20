"""Reply-first music: answer once Home Assistant accepts, verify afterwards."""

import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from declan.core import diagnostics
from declan.music import music
from declan.music.music_runtime_state import MusicRuntimeState
from test_music import MusicFixture
from result_pairs import pair_of


class ReplyFirstTests(MusicFixture):
    def setUp(self):
        super().setUp()
        self.enterContext(patch.dict(music.os.environ, {"DECLAN_MUSIC_REPLY_FIRST": "1"}))
        self.utility = "media_player.utility_queue"
        self.satellite = "assist_satellite.utility"
        self.players[self.utility] = {"entity_id": self.utility, "state": "idle", "attributes": {},
                                      "declan_area": "Utility Room", "declan_music_assistant": True}
        self.players[self.satellite] = {"entity_id": self.satellite, "state": "idle", "attributes": {},
                                        "declan_device": "utility-device", "declan_area": "Utility Room"}
        self.players[self.bedroom]["state"] = "idle"
        self.search_results = {"playlists": [{"name": "Country Music", "id": "A" * 22}]}

    def play_from_utility(self, origin="utility-device"):
        return pair_of(music.play_result)(music.parse("play country music"), ("http://ha", {}, self),
                          lambda _: (list(self.players.values()), None), origin=origin)

    def finish_background(self):
        for thread in threading.enumerate():
            if thread.name == "music-verify":
                thread.join(5)
                self.assertFalse(thread.is_alive())

    def announcements(self):
        return [data for name, data in self.calls if name == "announce"]

    def test_reply_is_requested_not_confirmed_and_playback_is_verified_later(self):
        reply, outcome = self.play_from_utility()
        self.assertEqual(outcome, "requested", reply)
        self.assertTrue(reply.startswith("Starting Country Music"), reply)
        self.finish_background()
        self.assertEqual(self.players[self.utility]["state"], "playing")
        self.assertEqual(self.announcements(), [])

    def test_failed_start_is_announced_on_the_originating_satellite(self):
        # Home Assistant accepts the request but the player never starts.
        self.play_response = lambda player, data: None
        reply, outcome = self.play_from_utility()
        self.assertEqual(outcome, "requested", reply)
        self.finish_background()
        self.assertEqual(len(self.announcements()), 1)
        announcement = self.announcements()[0]
        self.assertEqual(announcement["entity_id"], self.satellite)
        self.assertIn("couldn't confirm", announcement["message"])
        self.assertIs(announcement["preannounce"], False)

    def test_failed_start_without_a_satellite_is_not_announced(self):
        self.play_response = lambda player, data: None
        reply, outcome = self.play_from_utility(origin=self.utility)
        self.assertEqual(outcome, "requested", reply)
        self.finish_background()
        self.assertEqual(self.announcements(), [])

    def test_a_later_command_supersedes_the_pending_check(self):
        gate = threading.Event()
        calls = []

        def fake_wait_for(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                gate.wait(5)
                return False
            return True

        self.play_response = lambda player, data: None
        with patch.object(music, "wait_for", side_effect=fake_wait_for):
            reply, outcome = self.play_from_utility()
            self.assertEqual(outcome, "requested", reply)
            # The user pauses before the background check has finished.
            music.request(("http://ha", {}, self), "/api/services/media_player/media_pause",
                          {"entity_id": self.utility})
            gate.set()
            self.finish_background()
        self.assertEqual(self.announcements(), [])

    def test_timed_out_request_keeps_the_synchronous_verified_reply(self):
        def timeout(player, data):
            raise TimeoutError

        self.play_response = timeout
        reply, outcome = self.play_from_utility()
        self.assertNotEqual(outcome, "requested", reply)
        self.assertEqual([t.name for t in threading.enumerate() if t.name == "music-verify"], [])

    def test_verified_reply_is_used_when_the_option_is_turned_off(self):
        for value in ("0", "false", "No", " off "):
            with self.subTest(value=value), patch.dict(music.os.environ, {"DECLAN_MUSIC_REPLY_FIRST": value}):
                reply, outcome = self.play_from_utility()
                self.assertEqual(outcome, "confirmed", reply)
                self.assertEqual([t.name for t in threading.enumerate() if t.name == "music-verify"], [])

    def test_reply_first_is_on_by_default(self):
        for value in (None, "", "1", "yes"):
            env = {} if value is None else {"DECLAN_MUSIC_REPLY_FIRST": value}
            with self.subTest(value=value), patch.dict(music.os.environ, env, clear=False):
                if value is None:
                    music.os.environ.pop("DECLAN_MUSIC_REPLY_FIRST", None)
                self.assertTrue(music.reply_first_enabled())

    def test_late_result_is_added_to_the_saved_trace_without_changing_its_duration(self):
        with TemporaryDirectory() as folder, \
                patch.object(diagnostics, "DATABASE", Path(folder) / "diagnostics.sqlite3"):
            with diagnostics.request("/api/chat") as trace:
                self.play_from_utility()
            replied_in = trace["duration_ms"]
            self.finish_background()
            saved = diagnostics.recent()[0]
            stages = [stage for stage in saved["stages"] if stage["stage"] == "music_verification"]
            self.assertEqual(len(stages), 1)
            self.assertEqual(stages[0]["outcome"], "confirmed")
            self.assertEqual(stages[0]["player_entity_id"], self.utility)
            self.assertEqual(saved["duration_ms"], replied_in)
            self.assertEqual(saved["id"], trace["id"])


class OperationGenerationTests(unittest.TestCase):
    def test_only_the_latest_operation_is_current(self):
        state = MusicRuntimeState()
        first = state.begin_operation()
        self.assertTrue(state.is_current(first))
        second = state.begin_operation()
        self.assertFalse(state.is_current(first))
        self.assertTrue(state.is_current(second))


class DiagnosticsAmendTests(unittest.TestCase):
    def test_amend_ignores_a_trace_that_was_never_saved(self):
        trace = {"id": "abc", "stages": []}
        diagnostics.amend(trace, {"stage": "late"})
        self.assertEqual(trace["stages"], [])


if __name__ == "__main__":
    unittest.main()
