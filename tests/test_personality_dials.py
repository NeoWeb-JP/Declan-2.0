"""Personality sliders for the household and guests (Settings -> Household -> Personality)."""
import contextvars
import os
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from declan.ai import conversation_agent
from declan.core import history
from declan.http import settings_read_routes
from declan.turn import (
    conversation_entry,
    household_settings,
    line_freshness,
    personality,
    personality_dials,
    personality_policy,
)
from declan.voice import settings_voice_post
from test_household_settings import load_view

ROOT = Path(__file__).resolve().parents[1]
BASE = dict(personality_dials.BASE)


def dials(**changes):
    return {**BASE, **changes}


class FirstChoice:
    def choice(self, values):
        return min(values)


class Isolated(unittest.TestCase):
    def setUp(self):
        folder = Path(self.enterContext(TemporaryDirectory()))
        self.folder = folder
        self.enterContext(patch.object(personality_dials, "PATH", folder / "personality.json"))
        self.enterContext(patch.object(line_freshness, "PATH", folder / "line-freshness.sqlite3"))
        self.enterContext(patch.object(household_settings, "PATH", folder / "household-settings.json"))
        self.enterContext(patch.object(history, "DATABASE", folder / "conversations.sqlite3"))
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        # Each test gets its own "turn": nothing read about guests yet.
        self.context = contextvars.copy_context()
        self.context.run(personality_dials.reset_turn)

    def run_in_turn(self, function, *args, **kwargs):
        return self.context.run(function, *args, **kwargs)

    def save(self, household=None, guests=None):
        return personality_dials.save({"household": household or dict(BASE), "guests": guests or dict(BASE)})


class StorageTests(Isolated):
    def test_defaults_are_declan_as_he_was_for_both_sets(self):
        listing = personality_dials.listing()
        self.assertEqual(listing["settings"], {"household": BASE, "guests": BASE})
        self.assertEqual(listing["sources"], {"household": "default", "guests": "default"})
        self.assertEqual(listing["fingerprints"], {"household": "", "guests": ""})
        self.assertEqual(len(personality_dials.TRAITS), 7)
        self.assertEqual(personality_dials.LABELS["slang"], "Saffa-ness")

    def test_save_validates_and_keeps_the_sets_separate(self):
        for payload in ({}, {"household": BASE}, {"household": BASE, "guests": dials(sass=11)},
                        {"household": BASE, "guests": dials(sass=0)}, {"household": BASE, "guests": dials(sass=True)},
                        {"household": BASE, "guests": {**BASE, "extra": 1}}, [1]):
            with self.assertRaises(ValueError):
                personality_dials.save(payload)
        saved = self.save(guests=dials(swearing=1, insults=2))
        self.assertEqual(saved["settings"]["household"], BASE)
        self.assertEqual(saved["settings"]["guests"]["swearing"], 1)
        self.assertEqual(saved["fingerprints"]["household"], "")
        self.assertEqual(saved["fingerprints"]["guests"], "persona=8-8-7-6-5-1-2")
        self.assertEqual(personality_dials.from_fingerprint("persona=8-8-7-6-5-1-2"), dials(swearing=1, insults=2))
        for bad in ("", "persona=1-2", "persona=a-b-c-d-e-f-g", "persona=11-1-1-1-1-1-1", None):
            self.assertIsNone(personality_dials.from_fingerprint(bad))
        # A broken file gives the defaults.
        personality_dials.PATH.write_text("{nope", encoding="utf-8")
        self.assertEqual(personality_dials.dials("guests"), BASE)

    def test_a_change_forgets_learned_lines_for_old_sliders_only(self):
        with closing(sqlite3.connect(line_freshness.PATH)) as db, db:
            line_freshness._connect(line_freshness.PATH).close()
            rows = [("roast:home", "Old default line.", 1.0),
                    ("persona=1-1-1-1-1-1-1|roast:home", "Old tame line.", 1.0),
                    ("persona=8-8-7-6-5-1-2|roast:home", "Kept guest line.", 1.0)]
            db.executemany("INSERT INTO generated VALUES (?, ?, ?)", rows)
            db.executemany("INSERT INTO used VALUES (?, ?)", [("Old default line.", 5.0), ("Built in.", 5.0)])
            db.executemany("INSERT INTO attempts VALUES (?, ?)", [("roast:home", 5.0),
                                                                 ("persona=8-8-7-6-5-1-2|roast:home", 5.0)])
        saved = self.save(household=dials(sass=2), guests=dials(swearing=1, insults=2))
        self.assertEqual(saved["forgotten"], 2)
        with closing(sqlite3.connect(line_freshness.PATH)) as db, db:
            self.assertEqual([line for (line,) in db.execute("SELECT line FROM generated")], ["Kept guest line."])
            self.assertEqual([line for (line,) in db.execute("SELECT line FROM used")], ["Built in."])
            self.assertEqual([key for (key,) in db.execute("SELECT key FROM attempts")],
                             ["persona=8-8-7-6-5-1-2|roast:home"])
        # Saving the same sliders again forgets nothing.
        forget = Mock(return_value=0)
        again = personality_dials.save({"household": dials(sass=2), "guests": dials(swearing=1, insults=2)},
                                       forget=forget)
        forget.assert_not_called()
        self.assertEqual(again["forgotten"], 0)

    def test_a_failed_forget_still_saves(self):
        result = personality_dials.save({"household": dials(sass=1), "guests": BASE},
                                        forget=Mock(side_effect=sqlite3.OperationalError("locked")))
        self.assertIsNone(result["forgotten"])
        self.assertEqual(personality_dials.dials("household")["sass"], 1)


class WordingTests(Isolated):
    def test_swearing_insults_slang_and_length_rule_lines_out(self):
        shape = personality_dials.shape
        self.assertEqual(shape("Done, you lazy bastard.", BASE), "Done, you lazy bastard.")
        self.assertIsNone(shape("Done, you lazy bastard.", dials(swearing=5)))
        self.assertIsNone(shape("Put the fucking phone down.", dials(swearing=8)))
        self.assertEqual(shape("Bloody hell.", dials(swearing=4)), "Bloody hell.")
        self.assertIsNone(shape("Bloody hell.", dials(swearing=3)))
        self.assertIsNone(shape("There you go, you absolute muppet.", dials(insults=3)))
        self.assertIsNone(shape("There you go, you absolute muppet.", dials(insults=6)))
        self.assertEqual(shape("There you go, muppet.", dials(insults=4)), "There you go, muppet.")
        self.assertEqual(shape("Timer scheduled, my bru. Try to keep up.", dials(slang=2)),
                         "Timer scheduled. Try to keep up.")
        self.assertEqual(shape("What is my problem today, my bru?", dials(slang=1)), "What is my problem today?")
        self.assertIsNone(shape("Sleep lekker.", dials(slang=3)))
        long_line = "One two three four five six seven eight nine ten eleven twelve thirteen."
        self.assertIsNone(shape(long_line, dials(chattiness=3)))
        self.assertEqual(shape(long_line, dials(chattiness=4)), long_line)
        self.assertIsNone(shape("A short one with nine words in it, really.", dials(chattiness=1)))

    def test_gentle_and_extra_line_chance(self):
        self.assertFalse(personality_dials.gentle(BASE))
        self.assertTrue(personality_dials.gentle(dials(sass=2, rudeness=3, insults=3)))
        self.assertEqual(personality_dials.extra_line_chance(BASE), 1.0)
        self.assertEqual(personality_dials.extra_line_chance(dials(chattiness=1)), 0.0)
        self.assertLess(personality_dials.extra_line_chance(dials(sass=1, humour=1)), 0.2)
        self.assertTrue(personality_dials.wants_extra_line(BASE))
        self.assertFalse(personality_dials.wants_extra_line(dials(chattiness=1)))
        self.assertFalse(personality_dials.wants_extra_line(dials(sass=1, humour=1), random=Mock(random=lambda: 0.9)))

    def test_pick_follows_the_sliders_and_never_goes_silent(self):
        lines = ("Bloody marvellous, my bru.", "Done, you lazy bastard.", "Sorted.")
        self.save(household=dials(swearing=1, insults=1, slang=1))
        with patch.object(line_freshness, "_RANDOM", FirstChoice()):
            said = {self.run_in_turn(line_freshness.pick, "k", lines, now=1000.0 + i) for i in range(3)}
        self.assertEqual(said, {"Sorted."})
        # Every line ruled out: the tamest one, cleaned up.
        only = ("Bloody marvellous, my bru.", "Done, you lazy bastard.")
        self.assertEqual(self.run_in_turn(line_freshness.pick, "k2", only, now=2000.0), "Marvellous.")

    def test_fixed_sentences_follow_the_sliders(self):
        self.assertEqual(personality_dials.fixed("It's Christmas, boet! Zero sleeps.", BASE),
                         "It's Christmas, boet! Zero sleeps.")
        self.assertEqual(personality_dials.fixed("It's Christmas, boet! Zero sleeps.", dials(slang=1)),
                         "It's Christmas! Zero sleeps.")
        self.save(household=dials(slang=2))
        from declan.turn import christmas
        reply = self.run_in_turn(christmas.wifi_answer)
        self.assertEqual(reply, "Nobody's told me the Wi-Fi password. Ask your host.")

    def test_default_sliders_change_nothing(self):
        lines = ("Done, you lazy bastard.", "Bloody marvellous, my bru.")
        said = {self.run_in_turn(line_freshness.pick, "k", lines, now=1000.0 + i) for i in range(2)}
        self.assertEqual(said, set(lines))

    def test_generated_lines_are_kept_per_slider_fingerprint(self):
        self.save(guests=dials(swearing=1))
        key = "persona=8-8-7-6-5-1-8|k"
        with closing(sqlite3.connect(line_freshness.PATH)) as db, db:
            line_freshness._connect(line_freshness.PATH).close()
            db.execute("INSERT INTO generated VALUES (?, ?, ?)", (key, "Guest-only line.", 1.0))
            db.execute("INSERT INTO generated VALUES (?, ?, ?)", ("k", "Household line.", 1.0))
        start = Mock()

        def guest_turn():
            personality_dials.note_guest_mode("on")
            personality_dials.note_visitors(False)
            return {line_freshness.pick("k", ("Built in.",), now=1000.0 + i, topic="t", start=start) for i in range(3)}
        self.assertEqual(self.run_in_turn(guest_turn), {"Built in.", "Guest-only line."})
        self.assertEqual(start.call_args.args[0], key)

    def test_top_up_brief_follows_the_sliders(self):
        original = line_freshness.request_body("t", ["a"], 8, model="m", profile={}, polite=False, key="k")
        self.assertEqual(original["instructions"], line_freshness.INSTRUCTIONS)
        tame = line_freshness.request_body("t", ["a"], 8, model="m", profile={}, polite=False,
                                           key="persona=2-2-2-1-2-1-1|k")["instructions"]
        self.assertNotIn("rude, direct, sarcastic", tame)
        self.assertIn("Swearing: none at all.", tame)
        self.assertIn("never say 'my bru'", tame)
        self.assertIn("at most 12 words", tame)
        sent = Mock(return_value={"output_text": "Fair enough.\nBloody marvellous.\nSorted then."})
        config = {"model": "gpt-test", "profile": {}, "ceiling": 50_000, "monthly": 20_000_000, "key": "x"}
        with patch("declan.ai.ai_pricing.rate_pair", return_value=(1, 1)), \
             patch("declan.ai.ai_pricing.charge", return_value=1), \
             patch("declan.ai.model_response_results.ModelResponseResult.parse",
                   side_effect=lambda result: SimpleNamespace(
                       status=__import__("declan.ai.model_response_results", fromlist=["x"]).ModelResponseStatus.COMPLETED,
                       text=result["output_text"])):
            added = line_freshness.top_up("persona=2-2-2-1-2-1-1|k", "t", ["a"], config=config, send=sent,
                                          now=1_000_000.0)
        self.assertEqual(added, 2)
        self.assertNotIn("Bloody marvellous.", line_freshness.generated("persona=2-2-2-1-2-1-1|k"))


class AudienceTests(Isolated):
    def test_audience_follows_guest_mode_and_visitors(self):
        def turn(guest_mode, visitors):
            personality_dials.reset_turn()
            if guest_mode is not None:
                personality_dials.note_guest_mode(guest_mode)
            if visitors is not None:
                personality_dials.note_visitors(visitors)
            return personality_dials.current_audience()
        self.assertEqual(self.run_in_turn(turn, "off", False), "household")
        self.assertEqual(self.run_in_turn(turn, "on", False), "guests")
        self.assertEqual(self.run_in_turn(turn, "off", True), "guests")
        self.assertEqual(self.run_in_turn(turn, "off", None), "household")
        self.run_in_turn(personality_dials.reset_turn)
        self.assertEqual(self.run_in_turn(personality_dials.current_audience, True), "guests")
        self.assertEqual(self.run_in_turn(personality_dials.current_audience), "household")

    def test_low_sliders_use_the_gentler_lines_for_that_audience(self):
        self.assertFalse(household_settings.guest_lines(False))
        self.save(household=dials(sass=1, rudeness=1, insults=1))
        self.assertTrue(household_settings.guest_lines(False))
        self.assertFalse(household_settings.guest_lines(True))
        reply = self.run_in_turn(personality_policy.night_request_reply)
        gentle = {personality_policy.household_language.render(line) for line in personality_policy._NIGHT_GUEST}
        self.assertIn(reply.removeprefix("Good night. "), gentle)

    def test_chattiness_one_adds_no_extra_lines(self):
        self.save(household=dials(chattiness=1))

        def turn():
            personality_dials.note_guest_mode("off")
            personality_dials.note_visitors(False)
            return (personality.add_sass("Lights on.", "lights_on", "off"),
                    personality_policy.decorate("Done.", guest=False, visitor_present=False))
        self.assertEqual(self.run_in_turn(turn), ("Lights on.", "Done."))

    def test_conversation_agent_gets_the_listeners_persona(self):
        self.assertEqual(conversation_agent.instructions(), conversation_agent.INSTRUCTIONS)
        rude = conversation_agent.instructions(BASE)
        self.assertNotIn("polite household butler", rude)
        self.assertIn("Rudeness is high", rude)
        self.assertIn("Plain spoken English", rude)
        quiet = conversation_agent.instructions(dials(chattiness=2, slang=1, swearing=1))
        self.assertIn("under 15 words", quiet)
        self.assertIn("Swearing: none at all.", quiet)
        self.assertIn("Plain spoken British English", quiet)
        body = conversation_agent.request_body({}, {}, model="m", profile={}, persona=BASE)
        self.assertEqual(body["instructions"], rude)
        self.save(guests=dials(swearing=1))
        services = SimpleNamespace(read_guest_mode=lambda: "on", read_visitors_present=lambda: False)
        self.assertEqual(self.run_in_turn(conversation_entry.listener_persona, services)["swearing"], 1)
        broken = SimpleNamespace()
        self.assertEqual(self.run_in_turn(conversation_entry.listener_persona, broken), BASE)


class RouteTests(Isolated):
    def test_backend_routes_read_and_save(self):
        handler = SimpleNamespace(path="/api/settings/household", sent=[])
        handler.send_json = lambda status, payload: handler.sent.append((status, payload))
        settings_read_routes.dispatch(handler, voicepipeline=None, voice_profiles=None, diagnostics=None,
                                      history=None, ai_budget=None, ai_settings=None, ai_credentials=None,
                                      spotify_playlists=None)
        self.assertEqual(handler.sent[-1][1]["personality"]["settings"]["household"], BASE)
        names = ("spotify_save", "ai_replace_key", "ai_save", "ai_configured", "music", "spotify_playlists",
                 "playlist_handler", "opener_factory", "voice_manage", "pipeline_error", "profiles_manage",
                 "preview", "apply")
        settings_voice_post.dispatch(handler, {"save_personality": {"household": dials(sass=3), "guests": BASE}},
                                     **dict.fromkeys(names))
        status, payload = handler.sent[-1]
        self.assertEqual(status, 200)
        self.assertTrue(payload["saved"])
        self.assertEqual(payload["personality"]["settings"]["household"]["sass"], 3)
        settings_voice_post.dispatch(handler, {"save_personality": {"household": BASE}}, **dict.fromkeys(names))
        self.assertEqual(handler.sent[-1][0], 400)


class ViewTests(unittest.IsolatedAsyncioTestCase):
    async def test_view_validates_and_relays_the_sliders(self):
        module, session = load_view()
        response = MagicMock(status=200)
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=response)
        context.__aexit__ = AsyncMock(return_value=False)
        session.get.return_value = session.post.return_value = context
        entry = SimpleNamespace(data={"url": "http://declan", "token": "t" * 40})
        hass = SimpleNamespace(data={}, config_entries=SimpleNamespace(async_entries=lambda domain: [entry]))

        def request(body):
            class Request(dict):
                app: ClassVar[dict] = {"hass": hass}
                content_length = 40
                content_type = "application/json"

                async def json(self):
                    return body
            return Request(hass_user=SimpleNamespace(is_admin=True))
        view = module.DeclanHouseholdView()
        for body in ({"save_personality": {"household": BASE}},
                     {"save_personality": {"household": BASE, "guests": dials(sass=11)}},
                     {"save_personality": {"household": BASE, "guests": dials(sass="8")}}):
            self.assertEqual((await view.post(request(body)))["status"], 400)
        listing = {"settings": {"household": BASE, "guests": dials(swearing=1)},
                   "sources": {"household": "default", "guests": "saved"},
                   "traits": list(personality_dials.TRAITS), "labels": dict(personality_dials.LABELS),
                   "fingerprints": {"household": "", "guests": "x"}, "forgotten": 4}
        response.json = AsyncMock(return_value={"saved": True, "personality": listing})
        saved = await view.post(request({"save_personality": {"household": BASE, "guests": dials(swearing=1)}}))
        self.assertEqual(saved["status"], 200)
        self.assertEqual(saved["payload"]["personality"]["forgotten"], 4)
        self.assertNotIn("fingerprints", saved["payload"]["personality"])
        sources = dict.fromkeys(("guest_tone", "shelve_days", "fresh_lines", "christmas", "wifi_name",
                                 "wifi_password"), "saved")
        settings = {"guest_tone": "home", "shelve_days": 3, "fresh_lines": True, "christmas": "auto",
                    "wifi_name": "", "wifi_password": ""}
        response.json.return_value = {"settings": settings, "sources": sources, "personality": listing}
        read = await view.get(request(None))
        self.assertEqual(read["payload"]["personality"]["settings"]["guests"]["swearing"], 1)
        response.json.return_value = {"settings": settings, "sources": sources,
                                      "personality": {**listing, "settings": {"household": BASE}}}
        self.assertEqual((await view.get(request(None)))["status"], 502)

    def test_panel_has_both_slider_sets(self):
        panel = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text(encoding="utf-8")
        for text in ("personality-form", "save_personality", "personalitySliders('household')",
                     "personalitySliders('guests')", "'Saffa-ness'", "'Swearing'", "'Insults'"):
            self.assertIn(text, panel)


if __name__ == "__main__":
    unittest.main()
