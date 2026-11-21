"""FUT-44: "the usual" per room and time of day, run through ordinary commands."""
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from declan.core.execution_results import Outcome
from declan.turn import line_freshness, usual
from declan.turn.turn_dispatch_orchestration import DispatchResult

EVENING = datetime(2026, 11, 21, 19, 0, tzinfo=timezone.utc)
MORNING = datetime(2026, 11, 21, 7, 30, tzinfo=timezone.utc)


def result(reply, outcome):
    return DispatchResult(reply, outcome, *([None] * 7))


class UsualTests(unittest.TestCase):
    def setUp(self):
        folder = Path(self.enterContext(TemporaryDirectory()))
        self.path = folder / "usuals.sqlite3"
        self.enterContext(patch.object(usual, "PATH", self.path))
        self.enterContext(patch.object(line_freshness, "PATH", folder / "fresh.sqlite3"))
        self.enterContext(patch.object(line_freshness, "_start_top_up", Mock()))

    def test_run_phrases(self):
        for phrase in ("the usual", "The usual, Declan.", "the usual please", "do the usual", "same as usual",
                       "Howzit Declan, the usual", "can I have the usual", "I'll have the usual"):
            self.assertEqual(usual.match(phrase), ("run", None, None, None), phrase)
        for phrase in ("play music", "what's usually on tv", "unusual lights"):
            self.assertIsNone(usual.match(phrase), phrase)

    def test_set_ask_list_forget_phrases(self):
        self.assertEqual(
            usual.match("My usual for the lounge in the evening is lamps to 40% and play chill music"),
            ("set", "lounge", "evening", "lamps to 40% and play chill music"))
        self.assertEqual(usual.match("the usual for here is kitchen lights on"),
                         ("set", None, "any", "kitchen lights on"))
        self.assertEqual(usual.match("make lamps to 40% my usual for the master bedroom at night"),
                         ("set", "master bedroom", "night", "lamps to 40%"))
        self.assertEqual(usual.match("what's the usual?"), ("ask", None, None, None))
        self.assertEqual(usual.match("what's the usual for the lounge in the mornings"), ("ask", "lounge", "morning", None))
        self.assertEqual(usual.match("what are the usuals"), ("list", None, None, None))
        self.assertEqual(usual.match("forget the usual for the lounge in the evening"),
                         ("forget", "lounge", "evening", None))
        self.assertEqual(usual.match("forget the usual"), ("forget", None, "any", None))

    def test_steps_split_between_commands_not_inside_a_target(self):
        self.assertEqual(usual.steps_from("lamps to 40% and play chill music"), ["lamps to 40%", "play chill music"])
        self.assertEqual(usual.steps_from("turn on the kitchen and dining lights, then play rock"),
                         ["turn on the kitchen and dining lights", "play rock"])
        with self.assertRaises(ValueError):
            usual.steps_from("a, b, c, d, e, f")
        with self.assertRaises(ValueError):
            usual.steps_from("the usual")

    def test_windows(self):
        self.assertEqual(usual.window_at(MORNING), "morning")
        self.assertEqual(usual.window_at(datetime(2026, 1, 1, 13, tzinfo=timezone.utc)), "afternoon")
        self.assertEqual(usual.window_at(EVENING), "evening")
        self.assertEqual(usual.window_at(datetime(2026, 1, 1, 23, tzinfo=timezone.utc)), "night")
        self.assertEqual(usual.window_at(datetime(2026, 1, 1, 2, tzinfo=timezone.utc)), "night")

    def test_timed_usual_beats_any_time(self):
        usual.save("Lounge", "evening", "lamps to 40% and play chill music")
        usual.save("lounge", "any", ["lounge lights on"])
        self.assertEqual(usual.find("lounge", EVENING), ("evening", ["lamps to 40%", "play chill music"]))
        self.assertEqual(usual.find("lounge", MORNING), ("any", ["lounge lights on"]))
        self.assertIsNone(usual.find("kitchen", EVENING))

    def test_run_dispatches_each_step_in_the_room_with_sass(self):
        usual.save("lounge", "evening", "lamps to 40% and play chill music")
        replies = {"lamps to 40%": result("Lamps at 40%.", Outcome.CONFIRMED),
                   "play chill music": result("Playing chill music in the lounge.", Outcome.REQUESTED)}
        dispatch = Mock(side_effect=lambda phrase: replies[phrase])
        reply, outcome = usual.run("lounge", dispatch, moment=EVENING)
        self.assertEqual([call.args[0] for call in dispatch.call_args_list], ["lamps to 40%", "play chill music"])
        self.assertTrue(any(reply.startswith(line) for line in usual.LINES["run"]))
        self.assertTrue(reply.endswith("Lamps at 40%. Playing chill music in the lounge."))
        self.assertIs(outcome, Outcome.REQUESTED)

    def test_a_failed_step_is_reported_and_the_rest_still_run(self):
        usual.save("lounge", "any", "lamps to 40% and play chill music")
        replies = {"lamps to 40%": result("I couldn't find the lamps.", Outcome.UNRESOLVED),
                   "play chill music": result("Playing chill music.", Outcome.REQUESTED)}
        reply, outcome = usual.run("lounge", lambda phrase: replies[phrase], moment=EVENING)
        self.assertIn("I couldn't find the lamps.", reply)
        self.assertIn("Playing chill music.", reply)
        self.assertIs(outcome, Outcome.PARTIAL)

    def test_no_usual_or_unknown_room(self):
        dispatch = Mock()
        reply, outcome = usual.run("kitchen", dispatch, moment=EVENING)
        self.assertTrue(reply.startswith("You haven't told me the usual for the kitchen yet."))
        self.assertIs(outcome, Outcome.UNRESOLVED)
        reply, outcome = usual.run(None, dispatch, moment=EVENING)
        self.assertIn("Which room?", reply)
        dispatch.assert_not_called()

    def test_answer_set_ask_and_forget(self):
        reply = usual.answer(("set", None, "evening", "lamps to 40% and play chill music"), here="lounge")
        self.assertTrue(reply.endswith("The usual for the lounge in the evening: lamps to 40% and play chill music."))
        self.assertEqual(usual.answer(("ask", None, None, None), here="lounge", moment=EVENING),
                         "The usual for the lounge in the evening is lamps to 40% and play chill music.")
        self.assertEqual(usual.answer(("ask", None, None, None), here="lounge", moment=MORNING),
                         "You haven't told me the usual for the lounge yet.")
        self.assertIn("The lounge in the evening", usual.answer(("list", None, None, None), here=None))
        self.assertTrue(usual.answer(("forget", "lounge", "evening", None), here=None).startswith("Forgotten."))
        self.assertEqual(usual.listing(), [])

    def test_guests_can_run_but_not_change_it(self):
        reply = usual.answer(("set", "lounge", "any", "lights on"), here="lounge", guest=True)
        self.assertTrue(reply.startswith("Nice try"))
        self.assertEqual(usual.listing(), [])
        usual.save("lounge", "any", "lights on")
        self.assertTrue(usual.answer(("forget", "lounge", "any", None), here=None, guest=True).startswith("Nice try"))
        self.assertEqual(len(usual.listing()), 1)

    def test_survives_reopening_and_rejects_bad_input(self):
        usual.save("lounge", "night", ["lamps to 10%"])
        self.assertEqual(usual.listing()[0]["steps"], ["lamps to 10%"])
        with self.assertRaises(ValueError):
            usual.save("lounge", "lunchtime", ["lights on"])
        with self.assertRaises(ValueError):
            usual.save("<script>", "any", ["lights on"])
        with self.assertRaises(ValueError):
            usual.save("lounge", "any", [])


class TurnEntryUsualTests(unittest.TestCase):
    def setUp(self):
        folder = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(usual, "PATH", folder / "usuals.sqlite3"))
        self.enterContext(patch.object(line_freshness, "PATH", folder / "fresh.sqlite3"))
        self.enterContext(patch.object(line_freshness, "_start_top_up", Mock()))

    def services(self, guest="off", areas=None):
        from types import SimpleNamespace
        return SimpleNamespace(read_guest_mode=lambda: guest, ha_device_connection=lambda: ("url", {}, None),
                               read_ha_areas=Mock(return_value={"lounge": {"light.lamp"}} if areas is None else areas))

    def test_uses_the_room_that_heard_you(self):
        from declan.turn import turn_http_entry
        usual.save("lounge", "any", ["lamps to 40%"])
        services = self.services()
        dispatch = Mock(return_value=result("Lamps at 40%.", Outcome.CONFIRMED))
        answer = turn_http_entry._usual(("run", None, None, None), dispatch, services, "assist_satellite.lounge")
        services.read_ha_areas.assert_called_once_with(("url", {}, None), "assist_satellite.lounge")
        dispatch.assert_called_once_with("lamps to 40%")
        self.assertTrue(answer.reply.endswith("Lamps at 40%."))

    def test_guest_cannot_set_and_unknown_room_asks(self):
        from declan.turn import turn_http_entry
        answer = turn_http_entry._usual(("set", None, "any", "lights on"), Mock(), self.services(guest="on"), "sat")
        self.assertTrue(answer.reply.startswith("Nice try"))
        answer = turn_http_entry._usual(("ask", None, None, None), Mock(), self.services(areas={}), "sat")
        self.assertIn("Which room?", answer.reply)
        answer = turn_http_entry._usual(("set", None, "any", "lights on"), Mock(), self.services(), "sat")
        self.assertIs(answer.outcome, Outcome.CONFIRMED)
        self.assertEqual(usual.listing()[0]["room"], "lounge")


class HouseholdProxyUsualTests(unittest.TestCase):
    def test_change_bodies(self):
        from tests.test_household_settings import load_view
        view, _ = load_view()
        self.assertTrue(view.valid_usual_change(
            {"save_usual": {"room": "lounge", "window": "evening", "steps": ["lamps to 40%"]}}))
        self.assertTrue(view.valid_usual_change({"forget_usual": {"room": "lounge", "window": "any"}}))
        self.assertFalse(view.valid_usual_change({"save_usual": {"room": "lounge", "window": "noon", "steps": ["x"]}}))
        self.assertFalse(view.valid_usual_change({"save_usual": {"room": "lounge", "window": "any", "steps": []}}))
        self.assertFalse(view.valid_usual_change({"save_usual": {"room": "lounge", "window": "any",
                                                                 "steps": ["x"] * 6}}))
        self.assertTrue(view.valid_usuals(None))
        self.assertTrue(view.valid_usuals([{"room": "lounge", "window": "any", "steps": ["x"], "saved_at": 1.0}]))
        self.assertFalse(view.valid_usuals([{"room": "lounge", "window": "any", "steps": "x", "saved_at": 1.0}]))


if __name__ == "__main__":
    unittest.main()
