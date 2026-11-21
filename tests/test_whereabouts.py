"""FUT-42: "Where did I put...?" Local, shared, guest-proof, and the joke never replaces the answer."""
import os
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from declan.core.execution_results import Outcome
from declan.turn import line_freshness, turn_http_entry, whereabouts

LOCAL = datetime.now().astimezone().tzinfo
TUESDAY = datetime(2026, 11, 17, 18, 0, tzinfo=LOCAL).timestamp()
SATURDAY = datetime(2026, 11, 21, 9, 0, tzinfo=LOCAL).timestamp()


class Store(unittest.TestCase):
    def setUp(self):
        folder = Path(self.enterContext(TemporaryDirectory()))
        self.path = folder / "where.sqlite3"
        self.enterContext(patch.object(whereabouts, "PATH", self.path))
        self.enterContext(patch.object(line_freshness, "PATH", folder / "fresh.sqlite3"))
        self.enterContext(patch.object(line_freshness, "_start_top_up", Mock()))
        self.enterContext(patch.dict(os.environ, {}, clear=True))

    def ask(self, text, *, guest=False, now=SATURDAY):
        request = whereabouts.match(text)
        assert request is not None, text
        return whereabouts.answer(request, guest=guest, now=now)


class MatchTests(unittest.TestCase):
    def test_saving_finding_listing_and_forgetting_are_recognised(self):
        cases = {
            "the spare car key is in the hall drawer": ("save", ("spare car key", "in the hall drawer"), False),
            "Declan, the spare car key is in the hall drawer.": ("save", ("spare car key", "in the hall drawer"), False),
            "I put the passports in the safe": ("save", ("passports", "in the safe"), True),
            "I've moved the passports to the safe": ("save", ("passports", "in the safe"), True),
            "Edd has left his keys by the door": ("save", ("keys", "by the door"), True),
            "remember the spare key is under the mat": ("save", ("spare key", "under the mat"), True),
            "where's the spare car key?": ("find", ("spare car key", False), True),
            "where did I put my glasses": ("find", ("glasses", True), True),
            "have you seen my phone": ("find", ("phone", True), True),
            "where's edd's wallet": ("find", ("wallet", True), True),
            "what have I told you about": ("list", None, True),
            "forget the car key": ("forget", "car key", True),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(whereabouts.match(text), expected)

    def test_commands_and_chatter_are_not_filed(self):
        for text in ("the lights are on in the kitchen", "the kettle is on", "turn on the light in the hall",
                     "where is everyone", "the music is on in the lounge", "play jazz in the kitchen"):
            with self.subTest(text=text):
                self.assertNotEqual((whereabouts.match(text) or ("",))[0], "save")


class AnswerTests(Store):
    def test_save_then_find_with_the_joke_first(self):
        saved = self.ask("the spare car key is in the hall drawer", now=TUESDAY)
        self.assertIn(saved.split(" Spare car key:")[0], whereabouts.LINES["save"])
        self.assertTrue(saved.endswith("Spare car key: in the hall drawer."))
        found = self.ask("where's the spare car key?")
        joke, _, answer = found.rpartition(" In the hall drawer")
        self.assertIn(joke, whereabouts.LINES["found"])
        self.assertEqual(answer, ", since Tuesday.")

    def test_near_misses_and_plurals_match(self):
        self.ask("I put the spare car key in the hall drawer", now=TUESDAY)
        self.assertIn("In the hall drawer", self.ask("where are my car keys"))
        self.ask("the passport is in the safe", now=TUESDAY)
        self.assertIn("In the safe", self.ask("where's the pasport"))

    def test_moving_replaces_the_place_and_says_so(self):
        self.ask("the passports are in the drawer", now=TUESDAY)
        moved = self.ask("I've moved the passports to the safe")
        self.assertTrue(moved.endswith("Passports: in the safe. Moved from the drawer."))
        self.assertIn("In the safe", self.ask("where are the passports"))

    def test_second_ask_today_gets_the_lost_property_line(self):
        self.ask("the remote is under the cushion", now=TUESDAY)
        self.ask("where's the remote", now=SATURDAY)
        again = self.ask("where's the remote", now=SATURDAY + 60)
        self.assertTrue(again.startswith("Again? I'm starting a lost property office."))
        self.assertIn("Under the cushion", again)

    def test_unknown_things(self):
        self.assertIn("You never told me", self.ask("where did I put my glasses"))
        self.assertIsNone(self.ask("where is peru"))  # not personal: let general chat answer

    def test_guests_get_a_cheeky_refusal_and_no_location(self):
        self.ask("the spare key is under the mat", now=TUESDAY)
        for text in ("where's the spare key", "the gin is in the cupboard", "what have I told you about"):
            with self.subTest(text=text):
                reply = self.ask(text, guest=True)
                self.assertIn(reply, whereabouts.GUEST_LINES)
                self.assertNotIn("mat", reply)
        self.assertEqual([row["item"] for row in whereabouts.listing()], ["spare key"])

    def test_list_and_forget(self):
        self.assertIn("Nobody's told me", self.ask("what have I told you about"))
        self.ask("the spare key is under the mat", now=TUESDAY)
        self.ask("I put the passports in the safe", now=TUESDAY)
        self.assertIn("spare key", self.ask("what have I told you about"))
        self.assertEqual(self.ask("forget the spare key"), "Forgotten: spare key. Good luck finding it now.")
        self.assertIn("didn't know", self.ask("forget the spare key"))

    def test_since(self):
        self.assertEqual(whereabouts.since(SATURDAY - 3600, SATURDAY), "since earlier today")
        self.assertEqual(whereabouts.since(SATURDAY - 86400, SATURDAY), "since yesterday")
        self.assertEqual(whereabouts.since(datetime(2026, 11, 2, tzinfo=LOCAL).timestamp(), SATURDAY), "since 2 November")


class RequestTests(Store):
    def test_answered_locally_and_unknown_guest_mode_stays_private(self):
        services = SimpleNamespace(read_guest_mode=lambda: "off")
        result = turn_http_entry._whereabouts(whereabouts.match("I put the passports in the safe"), services)
        self.assertIs(result.outcome, Outcome.CHAT_ANSWER)
        broken = SimpleNamespace(read_guest_mode=Mock(side_effect=OSError))
        private = turn_http_entry._whereabouts(whereabouts.match("where are the passports"), broken)
        self.assertIn(private.reply, whereabouts.GUEST_LINES)
        self.assertIsNone(turn_http_entry._whereabouts(whereabouts.match("where is peru"), services))

    def test_settings_routes_list_and_forget(self):
        from declan.http import settings_read_routes
        from declan.turn import household_settings
        from declan.voice import settings_voice_post
        self.enterContext(patch.object(household_settings, "PATH", self.path.with_name("h.json")))
        self.ask("the spare key is under the mat", now=TUESDAY)
        handler = SimpleNamespace(path="/api/settings/household", sent=[])
        handler.send_json = lambda status, payload: handler.sent.append((status, payload))
        settings_read_routes.dispatch(handler, voicepipeline=None, voice_profiles=None, diagnostics=None,
                                      history=None, ai_budget=None, ai_settings=None, ai_credentials=None,
                                      spotify_playlists=None)
        self.assertEqual(handler.sent[-1][1]["whereabouts"][0]["item"], "spare key")
        names = ("spotify_save", "ai_replace_key", "ai_save", "ai_configured", "music", "spotify_playlists",
                 "playlist_handler", "opener_factory", "voice_manage", "pipeline_error", "profiles_manage",
                 "preview", "apply")
        settings_voice_post.dispatch(handler, {"forget_item": "spare key"}, **dict.fromkeys(names))
        self.assertEqual(handler.sent[-1], (200, {"forgotten": True}))
        self.assertEqual(whereabouts.listing(), [])


if __name__ == "__main__":
    unittest.main()
