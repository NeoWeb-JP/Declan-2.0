"""FUT-43: braai time runs existing commands with braai sass; partial failures are reported."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from declan.core.execution_results import Outcome
from declan.turn import braai, line_freshness
from declan.turn.turn_dispatch_orchestration import DispatchResult


def result(reply, outcome):
    return DispatchResult(reply, outcome, *([None] * 7))


class BraaiTests(unittest.TestCase):
    def setUp(self):
        folder = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(line_freshness, "PATH", folder / "fresh.sqlite3"))
        self.enterContext(patch.object(line_freshness, "_start_top_up", Mock()))

    def test_phrases(self):
        for phrase in ("braai time", "it's braai time", "we're having a braai", "start the braai", "fire up the braai"):
            self.assertEqual(braai.match(phrase), "start", phrase)
        for phrase in ("braai's over", "end the braai", "the braai is done"):
            self.assertEqual(braai.match(phrase), "end", phrase)
        for phrase in ("play braai music", "turn on the garden lights"):
            self.assertIsNone(braai.match(phrase))
        self.assertEqual(braai.how_long("how long on the chops?"), "how much time is left on the chops timer")
        self.assertIsNone(braai.how_long("what time is it"))

    def test_start_runs_music_lights_and_weather_with_sass(self):
        replies = {"play braai music": result("Starting braai music in the kitchen.", Outcome.REQUESTED),
                   "turn on the garden lights": result("Garden lights are on.", Outcome.CONFIRMED),
                   "will it rain today": result("Rain is likely today, 80%.", Outcome.CHAT_ANSWER)}
        dispatch = Mock(side_effect=lambda phrase: replies[phrase])
        reply, outcome = braai.run("start", dispatch)
        self.assertEqual([call.args[0] for call in dispatch.call_args_list], list(braai.STEPS))
        first = reply.split(" Starting braai music")[0]
        self.assertIn(first, braai.LINES["start"])
        self.assertIn("Garden lights are on.", reply)
        self.assertTrue(reply.endswith(braai.LINES["rain"][0]))
        self.assertIs(outcome, Outcome.REQUESTED)

    def test_a_failed_part_is_reported_and_the_rest_still_runs(self):
        replies = {"play braai music": result("Starting braai music.", Outcome.REQUESTED),
                   "turn on the garden lights": result("I couldn't find the garden lights.", Outcome.UNRESOLVED),
                   "will it rain today": result("No rain expected today.", Outcome.CHAT_ANSWER)}
        reply, outcome = braai.run("start", lambda phrase: replies[phrase])
        self.assertIn("I couldn't find the garden lights.", reply)
        self.assertNotIn(braai.LINES["rain"][0], reply)
        self.assertIs(outcome, Outcome.PARTIAL)

    def test_end_says_goodbye_without_stopping_the_house(self):
        dispatch = Mock()
        reply, outcome = braai.run("end", dispatch)
        self.assertIn(reply, braai.LINES["end"])
        self.assertIs(outcome, Outcome.CHAT_ANSWER)
        dispatch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
