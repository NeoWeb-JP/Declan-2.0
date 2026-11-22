"""FUT-50: "how are you, Declan?" gets uptime, today's misses and AI pocket money."""
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from declan.core.execution_results import Outcome
from declan.turn import self_report, turn_http_entry

NOW = datetime(2026, 11, 22, 15, 0).timestamp()


class SelfReportTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("declan.turn.line_freshness.pick", side_effect=lambda key, lines, **_: lines[0]))
        self.enterContext(patch.object(self_report, "STARTED", NOW - (3 * 86400 + 4 * 3600 + 120)))

    def report(self, guest=False, misses=(37, 2), spend=(7.123, 20.0)):
        with patch.object(self_report, "today_misses", return_value=misses), \
                patch.object(self_report, "spend", return_value=spend):
            return self_report.result(("self_report",), guest=guest, now=NOW)

    def test_phrases(self):
        for phrase in ("how are you, Declan?", "how are you", "how's it going", "status report",
                       "Hey Declan, how are you doing", "how are you my bru"):
            with self.subTest(phrase=phrase):
                self.assertEqual(self_report.match(phrase), ("self_report",))
        for other in ("how are you feeling about the lights", "how's the weather", "who are you", None):
            with self.subTest(phrase=other):
                self.assertIsNone(self_report.match(other))

    def test_full_report(self):
        result = self.report()
        self.assertEqual(result.outcome, Outcome.CHAT_ANSWER)
        self.assertEqual(result.reply, "Still standing, boet. I've been up 3 days and 4 hours. Today I didn't catch "
                                       "2 of your 37 requests. I've spent $7.12 of my $20.00 pocket money this month.")

    def test_many_misses_and_none(self):
        self.assertIn("Mumble less.", self.report(misses=(10, 3)).reply)
        self.assertIn("understood all 12 of your requests", self.report(misses=(12, 0)).reply)
        self.assertNotIn("Today", self.report(misses=(0, 0)).reply)

    def test_guests_get_no_household_numbers(self):
        reply = self.report(guest=True).reply
        self.assertIn("I've been up", reply)
        self.assertNotIn("$", reply)
        self.assertNotIn("requests", reply)

    def test_unreadable_numbers_are_left_out(self):
        with patch.object(self_report, "today_misses", side_effect=OSError), \
                patch.object(self_report, "spend", side_effect=KeyError):
            reply = self_report.result(("self_report",), guest=False, now=NOW).reply
        self.assertEqual(reply, "Still standing, boet. I've been up 3 days and 4 hours.")

    def test_uptime_wording(self):
        self.assertEqual(self_report.uptime(30), "1 minute")
        self.assertEqual(self_report.uptime(3600 + 60), "1 hour and 1 minute")
        self.assertEqual(self_report.uptime(2 * 86400), "2 days")

    def test_today_misses_reads_history_like_the_understanding_card(self):
        from declan.turn.command_vocabulary import UNMATCHED_REPLY
        rows = [("assist", "lights on", "Done.", "confirmed"),
                ("assist", "blah", UNMATCHED_REPLY, "unresolved"),
                ("browser_keyboard", "blah2", UNMATCHED_REPLY + " Try 'lights on'.", "unresolved"),
                ("assist", "lights on", "Done.", "duplicate"),
                ("internal", "x", UNMATCHED_REPLY, "unresolved")]

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, sql, params):
                self.params = params
                return SimpleNamespace(fetchall=lambda: rows)
        connection = Connection()
        with patch("declan.core.history.database", return_value=connection):
            self.assertEqual(self_report.today_misses(now=NOW), (3, 2))
        self.assertEqual(connection.params[0], datetime(2026, 11, 22).timestamp())

    def test_turn_entry_and_guest_mode(self):
        services = SimpleNamespace(read_guest_mode=lambda: "on")
        answer = turn_http_entry._self_report(("self_report",), services)
        self.assertNotIn("$", answer.reply)

    def test_mark_started(self):
        self_report.mark_started(123.0)
        self.assertEqual(self_report.STARTED, 123.0)


if __name__ == "__main__":
    unittest.main()
