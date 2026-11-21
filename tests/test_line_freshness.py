"""FUT-61: used lines rest for days; low pools are topped up in Declan's voice."""
import json
import os
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from declan.core import history
from declan.turn import household_settings, line_freshness, personality_policy, roast
from declan.turn.response_rotation_state import ResponseRotationState

DAY = 86400
LINES = ("One.", "Two.", "Three.", "Four.", "Five.")


class FirstChoice:
    def choice(self, values):
        return min(values)


class FreshnessTests(unittest.TestCase):
    def setUp(self):
        folder = Path(self.enterContext(TemporaryDirectory()))
        self.path = folder / "line-freshness.sqlite3"
        self.enterContext(patch.object(line_freshness, "PATH", self.path))
        self.enterContext(patch.object(household_settings, "PATH", folder / "household-settings.json"))
        self.enterContext(patch.object(history, "DATABASE", folder / "conversations.sqlite3"))
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.start = Mock()

    def pick(self, now, lines=LINES, topic=None, key="personality:weather:False"):
        return line_freshness.pick(key, lines, topic=topic, now=now, start=self.start)

    def test_used_lines_rest_for_the_shelve_period_across_restarts(self):
        said = [self.pick(1000.0 + i) for i in range(5)]
        self.assertEqual(sorted(said), sorted(LINES))  # every line once before any repeats
        # A "restart": the module keeps nothing in memory, it's all on disk.
        self.assertEqual(sqlite3.connect(self.path).execute("SELECT COUNT(*) FROM used").fetchone()[0], 5)
        # All resting: the one rested longest is used, never silence.
        self.assertEqual(self.pick(2000.0), said[0])
        # Just under three days later the others are rested again; the line used at 2000 isn't.
        later = [self.pick(2000.0 + 3 * DAY - 10 + i) for i in range(4)]
        self.assertNotIn(said[0], later)

    def test_shelve_days_setting_and_zero_turns_resting_off(self):
        household_settings.save({"guest_tone": "home", "shelve_days": 0})
        with patch.object(line_freshness, "_RANDOM", FirstChoice()):
            self.assertEqual({self.pick(1000.0 + i) for i in range(3)}, {"Five."})

    def test_generated_lines_join_the_pool(self):
        with sqlite3.connect(self.path) as db:
            line_freshness._connect(self.path).close()
            db.execute("INSERT INTO generated VALUES (?, ?, ?)", ("personality:weather:False", "Eish, boet.", 1.0))
        said = {self.pick(1000.0 + i) for i in range(6)}
        self.assertIn("Eish, boet.", said)
        self.assertEqual(line_freshness.generated("personality:weather:False"), ["Eish, boet."])

    def test_low_pool_starts_one_top_up_only_with_a_topic_and_fresh_lines_on(self):
        for i in range(2):
            self.pick(1000.0 + i)
        self.start.assert_not_called()
        self.pick(1002.0, topic="after giving the weather")
        self.start.assert_called_once()
        key, topic, pool, polite, _ = self.start.call_args.args
        self.assertEqual((key, topic, polite), ("personality:weather:False", "after giving the weather", False))
        self.assertEqual(set(pool), set(LINES))
        self.start.reset_mock()
        household_settings.save({"guest_tone": "home", "fresh_lines": False})
        self.pick(1003.0, topic="after giving the weather")
        self.start.assert_not_called()

    def test_storage_failure_falls_back_to_a_random_line(self):
        with patch.object(line_freshness, "_connect", side_effect=sqlite3.OperationalError("locked")):
            self.assertIn(self.pick(1000.0), LINES)
        self.assertEqual(line_freshness.pick("k", (), start=self.start), "")

    def test_rotation_state_with_a_namespace_uses_the_store(self):
        state = ResponseRotationState(namespace="policy")
        with patch.object(line_freshness, "pick", return_value="Two.") as pick:
            self.assertEqual(state.choose(("home", "night"), LINES, topic="t", polite=True), "Two.")
        self.assertEqual(pick.call_args.args[0], "policy:home:night")
        self.assertEqual(pick.call_args.kwargs, {"topic": "t", "polite": True})
        # Without a namespace (tests, injected randomness) nothing is stored.
        self.assertEqual(ResponseRotationState(random=FirstChoice()).choose("k", LINES), "Five.")
        self.assertFalse(self.path.exists())

    def test_policy_and_roasts_pass_topics_and_tone(self):
        with patch.object(line_freshness, "pick", side_effect=lambda key, lines, **kwargs: lines[0]) as pick:
            personality_policy.night_request_reply()
            self.assertEqual(pick.call_args.args[0], "policy:home:night")
            self.assertEqual(pick.call_args.kwargs["topic"], line_freshness.TOPICS["night"])
            self.assertIn("Mike", roast.respond("Mike", guest=False))


class ValidationTests(unittest.TestCase):
    def test_good_lines_pass_and_are_tidied(self):
        self.assertEqual(line_freshness.valid_line("1. Lekker, boet", []), "Lekker, boet.")
        self.assertEqual(line_freshness.valid_line('"Eish, {pet_dog} is judging you!"', []),
                         "Eish, {pet_dog} is judging you!")

    def test_claims_numbers_long_lines_odd_placeholders_and_duplicates_fail(self):
        existing = ["Done, you lazy bastard. I should start charging by the sigh."]
        for line in ("The lights are now on, boet.", "Set to fifty percent.", "Timer is set, my bru.",
                     "It's 20 degrees.", "That failed, sorry.", "word " * 23, "Hello {owner}.",
                     "Unclosed { brace.", "Done, you lazy bastard, I should start charging by the sigh.",
                     "Emoji 😀 here.", "", None):
            with self.subTest(line=line):
                self.assertIsNone(line_freshness.valid_line(line, existing))

    def test_topics(self):
        self.assertEqual(line_freshness.topic_for("home", "movie", "start"), "movie night (start)")
        self.assertEqual(line_freshness.topic_for("weather"), "after giving the weather")
        self.assertIsNone(line_freshness.topic_for("unknown"))


class TopUpTests(unittest.TestCase):
    def setUp(self):
        folder = Path(self.enterContext(TemporaryDirectory()))
        self.path = folder / "line-freshness.sqlite3"
        self.enterContext(patch.object(line_freshness, "PATH", self.path))
        self.enterContext(patch.object(history, "DATABASE", folder / "conversations.sqlite3"))
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.config = {"model": "gpt-5-mini", "profile": {"reasoning_effort": "minimal"}, "key": "k",
                       "monthly": 20_000_000, "ceiling": 50_000}

    def reply(self, text):
        return {"status": "completed", "usage": {"input_tokens": 400, "output_tokens": 200},
                "output": [{"type": "message", "role": "assistant",
                            "content": [{"type": "output_text", "text": text}]}]}

    def top_up(self, text, *, now=1_000_000.0, examples=("Done, boet.",), send=None):
        send = send or Mock(return_value=self.reply(text))
        with patch("declan.ai.ai_pricing.rate_pair", return_value=(1, 1)), \
                patch("declan.ai.ai_pricing.charge", return_value=1234):
            added = line_freshness.top_up("personality:weather:False", "after giving the weather", list(examples),
                                          now=now, config=self.config, send=send)
        return added, send

    def test_valid_lines_are_stored_and_bad_ones_dropped(self):
        added, send = self.top_up("Eish, the sky has opinions, boet.\nThe lights are now on.\n"
                                  "Ja nee, umbrellas exist for a reason.\nDone, boet.\n{pet_dog} wants a walk.")
        self.assertEqual(added, 2)
        self.assertEqual(line_freshness.generated("personality:weather:False"),
                         ["Eish, the sky has opinions, boet.", "Ja nee, umbrellas exist for a reason."])
        body = send.call_args.args[0]
        self.assertEqual(json.loads(body["input"])["topic"], "after giving the weather")
        self.assertFalse(body["store"])
        self.assertIn("South African", body["instructions"])
        # Charged the settled cost, capped at the request's worst case.
        self.assertTrue(0 < line_freshness.month_spent(now=1_000_000.0) <= 1234)

    def test_retry_window_cap_budget_and_missing_model(self):
        self.top_up("Eish, boet.")
        added, send = self.top_up("Lekker weather, boet.", now=1_000_100.0)
        self.assertEqual(added, 0)
        send.assert_not_called()  # tried within the last 12 hours
        with patch.dict(os.environ, {line_freshness.BUDGET_ENVIRONMENT: "0"}):
            added, send = self.top_up("Lekker weather, boet.", now=1_100_000.0)
        self.assertEqual(added, 0)
        send.assert_not_called()
        from declan.ai import general_chat
        with patch.object(general_chat, "model_config", side_effect=general_chat.ModelUnavailable("no key")):
            self.assertEqual(line_freshness.top_up("x", "t", [], now=1_200_000.0), 0)

    def test_failed_request_is_charged_safely_and_adds_nothing(self):
        added, _ = self.top_up("", send=Mock(side_effect=OSError("down")))
        self.assertEqual(added, 0)
        self.assertEqual(line_freshness.generated("personality:weather:False"), [])

    def test_polite_tone_and_listing_and_delete(self):
        body = line_freshness.request_body("t", ["a"], 8, model="m", profile={}, polite=True)
        self.assertIn("no swearing", body["instructions"])
        self.top_up("Eish, the sky has opinions, boet.")
        listing = line_freshness.listing(now=1_000_000.0)
        self.assertEqual([row["line"] for row in listing["lines"]], ["Eish, the sky has opinions, boet."])
        self.assertEqual(listing["budget_micro_usd"], 1_000_000)
        self.assertTrue(line_freshness.delete("personality:weather:False", "Eish, the sky has opinions, boet."))
        self.assertFalse(line_freshness.delete("personality:weather:False", "missing"))
        with self.assertRaises(ValueError):
            line_freshness.delete(None, "x")


class RouteTests(unittest.TestCase):
    def test_household_routes_list_and_delete_generated_lines(self):
        from declan.http import settings_read_routes
        from declan.voice import settings_voice_post
        folder = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(line_freshness, "PATH", folder / "f.sqlite3"))
        self.enterContext(patch.object(household_settings, "PATH", folder / "h.json"))
        handler = SimpleNamespace(path="/api/settings/household", sent=[])
        handler.send_json = lambda status, payload: handler.sent.append((status, payload))
        settings_read_routes.dispatch(handler, voicepipeline=None, voice_profiles=None, diagnostics=None,
                                      history=None, ai_budget=None, ai_settings=None, ai_credentials=None,
                                      spotify_playlists=None)
        self.assertEqual(handler.sent[-1][1]["generated"]["lines"], [])
        names = ("spotify_save", "ai_replace_key", "ai_save", "ai_configured", "music", "spotify_playlists",
                 "playlist_handler", "opener_factory", "voice_manage", "pipeline_error", "profiles_manage",
                 "preview", "apply")
        settings_voice_post.dispatch(handler, {"delete_line": {"key": "a", "line": "b"}}, **dict.fromkeys(names))
        self.assertEqual(handler.sent[-1], (200, {"deleted": False}))
        settings_voice_post.dispatch(handler, {"delete_line": {"key": 1}}, **dict.fromkeys(names))
        self.assertEqual(handler.sent[-1][0], 400)
        settings_voice_post.dispatch(handler, {"settings": {"guest_tone": "home", "shelve_days": 5}},
                                     **dict.fromkeys(names))
        self.assertEqual(handler.sent[-1][1]["settings"]["shelve_days"], 5)


if __name__ == "__main__":
    unittest.main()
