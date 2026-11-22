"""FUT-67: Spotify and Music Assistant reliability under failures and simultaneous requests."""
from threading import Event, Thread
from unittest.mock import patch
from urllib.error import URLError

import test_music as music_fixture
from declan.music import music
from result_pairs import pair_of


class MusicReliabilityTests(music_fixture.MusicFixture):
    def setUp(self):
        super().setUp()
        self.players[self.bedroom].update(state="idle", attributes={})
        self.poll_failures = 0

    def open(self, request, timeout):
        if request.data is None and "/api/states/" in request.full_url and self.poll_failures:
            self.poll_failures -= 1
            raise URLError("connection reset by peer")
        return super().open(request, timeout)

    def play_media_calls(self):
        return [data for name, data in self.calls if name == "play_media"]

    def test_a_dropped_state_poll_does_not_throw_away_verification(self):
        self.poll_failures = 1
        reply, outcome = self.play("play yellow in the kitchen")
        self.assertEqual(outcome, "confirmed", reply)
        self.assertEqual(len(self.play_media_calls()), 1)

    def test_polls_that_never_answer_end_unverified_without_resending(self):
        self.poll_failures = 10_000
        reply, outcome = self.play("play yellow in the kitchen")
        self.assertEqual(outcome, "unverified", reply)
        self.assertEqual(len(self.play_media_calls()), 1)

    def test_a_timed_out_play_request_is_never_sent_twice(self):
        real = music_fixture.MusicFixture.open

        def slow_play(request, timeout):
            response = real(self, request, timeout)
            if request.full_url.endswith("/play_media"):
                raise TimeoutError("Home Assistant took too long")
            return response
        with patch.object(self, "open", side_effect=slow_play):
            reply, outcome = self.play("play yellow in the kitchen")
        self.assertEqual(len(self.play_media_calls()), 1)
        self.assertEqual(outcome, "confirmed", reply)  # it did start; polling saw it

    def test_simultaneous_requests_never_start_two_streams(self):
        entered, release = Event(), Event()
        real = music_fixture.MusicFixture.open

        def held(request, timeout):
            if request.full_url.endswith("/play_media"):
                entered.set()
                release.wait(3)
            return real(self, request, timeout)
        results = []
        with patch.object(self, "open", side_effect=held):
            first = Thread(target=lambda: results.append(self.play("play yellow in the kitchen")))
            first.start()
            self.assertTrue(entered.wait(3))
            second = self.play("play rock in the bedroom")
            release.set()
            first.join(5)
        self.assertEqual(second[1], "busy", second[0])
        self.assertEqual(len(self.play_media_calls()), 1)
        self.assertEqual(results[0][1], "confirmed", results[0][0])

    def test_an_unexpected_failure_releases_the_music_lock(self):
        def broken(_connection):
            raise TypeError("bad inventory row")
        with self.assertRaises(TypeError):
            pair_of(music.play_result)(music.parse("play yellow in the kitchen"), ("http://ha", {}, self), broken)
        reply, outcome = self.play("play yellow in the kitchen")
        self.assertEqual(outcome, "confirmed", reply)

    def test_an_unavailable_player_is_reported_and_not_called(self):
        self.players[self.kitchen]["state"] = "unavailable"
        reply, outcome = self.play("play yellow in the kitchen")
        self.assertEqual(outcome, "unavailable", reply)
        self.assertEqual(self.play_media_calls(), [])

    def test_rate_limited_playback_is_reported_once_and_not_retried(self):
        self.throttled = True
        reply, outcome = self.play("play yellow in the kitchen")
        self.assertEqual(outcome, "unverified")
        self.assertIn("rate limited", reply)
        self.assertEqual(sum(1 for name, _ in self.calls if name == "play_media"), 1)


if __name__ == "__main__":
    import unittest
    unittest.main()
