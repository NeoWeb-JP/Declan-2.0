"""FUT-59: Christmas mode, the countdown, cooking timers, Boxing Day and the guest Wi-Fi."""
import os
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from declan.core.execution_results import Outcome
from declan.music import music
from declan.timers.timers import duration_seconds
from declan.turn import (
    christmas,
    compound_commands,
    household_settings,
    line_freshness,
    personality,
    personality_policy,
    turn_dispatch_orchestration,
    turn_http_entry,
)

DEC_10, DEC_26, JAN_2, JAN_3, NOV_21 = (date(2026, 12, 10), date(2026, 12, 26), date(2027, 1, 2),
                                        date(2027, 1, 3), date(2026, 11, 21))


class Settings(unittest.TestCase):
    def setUp(self):
        folder = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(household_settings, "PATH", folder / "household.json"))
        self.enterContext(patch.object(line_freshness, "PATH", folder / "fresh.sqlite3"))
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.enterContext(patch.object(line_freshness, "_start_top_up", Mock()))

    def set_mode(self, value):
        household_settings.save({"guest_tone": "home", "christmas": value})


class ModeTests(Settings):
    def test_automatic_season_and_manual_override(self):
        for day, expected in ((NOV_21, False), (DEC_10, True), (JAN_2, True), (JAN_3, False)):
            with self.subTest(day=day):
                self.assertEqual(christmas.active(day), expected)
        self.set_mode("on")
        self.assertTrue(christmas.active(NOV_21))
        self.set_mode("off")
        self.assertFalse(christmas.active(DEC_10))

    def test_voice_requests_are_recognised(self):
        cases = {"christmas mode on": ("mode", "on"), "turn on christmas mode": ("mode", "on"),
                 "switch off christmas mode": ("mode", "off"), "end christmas": ("mode", "off"),
                 "start christmas mode": ("mode", "on"), "is it christmas mode": ("mode", "status"),
                 "How many sleeps till Christmas?": ("sleeps", None), "how long until christmas": ("sleeps", None),
                 "what's the wifi password": ("wifi", None), "wi-fi password": ("wifi", None),
                 "play christmas music": None, "christmas morning": None}
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(christmas.match(phrase), expected)

    def test_voice_mode_change_is_saved_with_a_line(self):
        reply = christmas.answer(("mode", "on"), today=NOV_21)
        self.assertIn(reply, christmas.LINES["mode_on"])
        self.assertEqual(christmas.mode(), "on")
        self.assertIn(christmas.answer(("mode", "off")), christmas.LINES["mode_off"])
        self.assertFalse(christmas.active(DEC_10))
        self.assertIn("off right now", christmas.answer(("mode", "status"), today=DEC_10))

    def test_sleeps(self):
        self.assertEqual(christmas.sleeps(DEC_10), 15)
        self.assertEqual(christmas.sleeps(DEC_26), 364)
        self.assertTrue(christmas.answer(("sleeps", None), today=NOV_21).startswith("34 sleeps till Christmas."))
        self.assertEqual(christmas.answer(("sleeps", None), today=NOV_21), "34 sleeps till Christmas.")
        self.assertTrue(christmas.answer(("sleeps", None), today=date(2026, 12, 24)).startswith("One sleep"))
        self.assertIn("Zero sleeps", christmas.answer(("sleeps", None), today=date(2026, 12, 25)))
        with patch.object(christmas, "date", Mock(today=Mock(return_value=DEC_10), side_effect=date)):
            reply = christmas.answer(("sleeps", None), today=DEC_10)
        self.assertTrue(reply.startswith("15 sleeps till Christmas. "))

    def test_wifi_answer(self):
        self.assertIn("Nobody's told me", christmas.answer(("wifi", None)))
        household_settings.save({"guest_tone": "home", "wifi_name": "Braai Guests", "wifi_password": "boerewors1"})
        reply = christmas.answer(("wifi", None))
        self.assertEqual(reply, "The Wi-Fi is Braai Guests. The password is boerewors1. "
                                "Spelled out: b o e r e w o r s 1.")
        for bad in ("x" * 64, "café"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                household_settings.save({"guest_tone": "home", "wifi_password": bad})


class SeasonalLineTests(Settings):
    def test_seasonal_categories_and_boxing_day(self):
        self.assertIsNone(christmas.seasonal("lights_on", today=NOV_21, coin=0.0))
        self.assertEqual(christmas.seasonal("lights_on", today=DEC_10, coin=0.0), "lights_on")
        self.assertIsNone(christmas.seasonal("lights_on", today=DEC_10, coin=0.9))
        self.assertIsNone(christmas.seasonal("weather", today=DEC_10, coin=0.0))
        self.assertEqual(christmas.seasonal("good_morning", today=DEC_26, coin=0.9), "boxing_day")

    def test_everyday_lines_get_christmas_ones_while_the_mode_is_on(self):
        self.set_mode("on")
        with patch.object(christmas._RANDOM, "random", return_value=0.0), \
                patch("declan.turn.command_responses.selected", return_value=None):
            self.assertIn(personality.choose_line("timer_set", "off"), christmas.LINES["timer_set"])
            reply = personality_policy.decorate("Done.", outcome="confirmed")
            self.assertIn(reply.removeprefix("Done. "), christmas.LINES["general"])
            self.assertIn(personality_policy.night_request_reply().removeprefix("Good night. "),
                          christmas.LINES["night"])
        self.set_mode("off")
        with patch("declan.turn.command_responses.selected", return_value=None):
            self.assertNotIn(personality.choose_line("timer_set", "off"), christmas.LINES["timer_set"])

    def test_a_reply_with_a_just_picked_line_is_not_decorated_twice(self):
        self.set_mode("on")
        with patch.object(christmas._RANDOM, "random", return_value=0.0):
            first = christmas.pick("mode_on")
            self.assertEqual(personality_policy.decorate(first, outcome="confirmed"), first)

    def test_boxing_day_starts_music_quieter(self):
        self.set_mode("on")
        with patch.object(music.music_settings, "start_volume", return_value=(30, "default")):
            with patch.object(christmas, "boxing_day", return_value=True):
                self.assertEqual(music.start_volume(), 0.2)
            with patch.object(christmas, "boxing_day", return_value=False):
                self.assertEqual(music.start_volume(), 0.3)
        with patch.object(music.music_settings, "start_volume", return_value=(10, "saved")), \
                patch.object(christmas, "boxing_day", return_value=True):
            self.assertEqual(music.start_volume(), 0.1)

    def test_play_some_music_prefers_christmas_playlists(self):
        festive = "spotify://playlist/" + "c" * 22
        catalogue = {"categories": {"christmas": {"playlists": [festive]},
                                    "rock": {"playlists": ["spotify://playlist/" + "r" * 22]}}}
        with patch("declan.music.spotify_playlists.listing", return_value=catalogue):
            self.set_mode("on")
            self.assertEqual(music.generic_selection({})[2], "Christmas music")
            self.set_mode("off")
            self.assertEqual(music.generic_selection({})[2], "rock music")
        self.assertIn("christmas", __import__("declan.music.spotify_playlists", fromlist=["x"]).CATEGORIES)


class CookingTimerTests(unittest.TestCase):
    def split(self, phrase):
        return compound_commands.split_timers(phrase, duration_seconds=duration_seconds)

    def test_several_timers_in_one_sentence(self):
        expected = ["set a turkey timer for 3 hours", "set a roast potatoes timer for 50 minutes"]
        for phrase in ("set a turkey timer for 3 hours and a roast potatoes timer for 50 minutes",
                       "turkey 3 hours, roast potatoes 50 minutes",
                       "set timers for turkey 3 hours and roast potatoes 50 minutes",
                       "3 hours for the turkey and 50 minutes for the roast potatoes"):
            with self.subTest(phrase=phrase):
                self.assertEqual(sorted(self.split(phrase)), sorted(expected))
        self.assertEqual(self.split("set a turkey timer for 1 hour and 30 minutes and a pudding timer for 20 minutes"),
                         ["set a turkey timer for 1 hour and 30 minutes", "set a pudding timer for 20 minutes"])

    def test_everything_else_stays_whole(self):
        for phrase in ("set a timer for 10 minutes", "set a turkey timer for 3 hours",
                       "turn on the kitchen and lounge lights", "play rock for 3 hours and lights on",
                       "turkey 3 hours and turn on the lights"):
            with self.subTest(phrase=phrase):
                self.assertIsNone(self.split(phrase))

    def test_each_timer_is_dispatched_and_replies_combined(self):
        results = iter([SimpleNamespace(reply="Turkey timer set.", outcome=Outcome.CONFIRMED),
                        SimpleNamespace(reply="Potatoes timer set.", outcome=Outcome.UNAVAILABLE)])
        seen = []

        def fake(command, **kwargs):
            seen.append(command)
            result = next(results)
            return turn_dispatch_orchestration.DispatchResult(result.reply, result.outcome,
                                                               *([None] * 7))
        with patch.object(turn_dispatch_orchestration, "dispatch", side_effect=fake):
            combined = turn_dispatch_orchestration._dispatch_many(["a", "b"], source="assist")
        self.assertEqual(seen, ["a", "b"])
        self.assertEqual(combined.reply, "Turkey timer set. Potatoes timer set.")
        self.assertIs(combined.outcome, Outcome.PARTIAL)


class RequestTests(Settings):
    def test_christmas_requests_are_answered_locally(self):
        result = turn_http_entry._christmas(("mode", "on"))
        self.assertIs(result.outcome, Outcome.CONFIRMED)
        self.assertIn(result.reply, christmas.LINES["mode_on"])
        self.assertIs(turn_http_entry._christmas(("wifi", None)).outcome, Outcome.CHAT_ANSWER)
        with patch.object(christmas, "answer", side_effect=OSError):
            self.assertIs(turn_http_entry._christmas(("mode", "off")).outcome, Outcome.FAILED)

    def test_guest_mode_on_gets_its_own_lines(self):
        self.assertIn("guest_on", personality.LINES)
        self.assertEqual(christmas.CATEGORY_MAP["guest_on"], "guest_on")


if __name__ == "__main__":
    unittest.main()
