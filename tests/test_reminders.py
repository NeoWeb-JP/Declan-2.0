"""FUT-26: timed reminders on the timer engine (ring until "stop", like a timer)."""
import os
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from declan.core.execution_results import Outcome
from declan.timers import reminders, timers

LOCAL = datetime.now().astimezone().tzinfo
SATURDAY_10AM = datetime(2026, 11, 21, 10, 0, tzinfo=LOCAL)


class ParseTests(unittest.TestCase):
    def when(self, phrase):
        result = reminders.parse(phrase, now=SATURDAY_10AM)
        assert result is not None and result[0] == "set", phrase
        return result[1], datetime.fromtimestamp(result[2], LOCAL).strftime("%a %H:%M") if result[2] else None

    def test_times_and_messages(self):
        cases = {
            "remind me at six to put the bins out": ("reminder: put the bins out", "Sat 18:00"),
            "remind me in 20 minutes to check the oven": ("reminder: check the oven", "Sat 10:20"),
            "remind me to check the oven in 20 minutes": ("reminder: check the oven", "Sat 10:20"),
            "remind edd tomorrow at 8 to call the plumber": ("reminder: Edd: call the plumber", "Sun 08:00"),
            "remind me at 6:30 pm to feed the dog": ("reminder: feed the dog", "Sat 18:30"),
            "remind me at half past seven to call mum": ("reminder: call mum", "Sat 19:30"),
            "remind me at noon to take the washing in": ("reminder: take the washing in", "Sat 12:00"),
            "set a reminder for 9 am to call the bank": ("reminder: call the bank", "Sun 09:00"),
            "remind me at 9 tomorrow that I need to go": ("reminder: go", "Sun 09:00"),
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(self.when(phrase), expected)
        self.assertEqual(self.when("remind me at 25 to x"), ("reminder: x", None))

    def test_list_cancel_and_non_reminders(self):
        self.assertEqual(reminders.parse("what reminders do I have"), ("list",))
        self.assertEqual(reminders.parse("cancel the bins reminder"), ("cancel", "bins"))
        self.assertEqual(reminders.parse("cancel the reminder to call mum"), ("cancel", "call mum"))
        self.assertEqual(reminders.parse("cancel my reminders"), ("cancel", None))
        for phrase in ("cancel the pasta timer", "set a tea timer for 5 minutes", "turn on the lights", "remind me"):
            with self.subTest(phrase=phrase):
                self.assertIsNone(reminders.parse(phrase))
        self.assertEqual(reminders.spoken("reminder: Edd: call the plumber"), "Reminder for Edd: call the plumber.")
        self.assertEqual(reminders.spoken("reminder: put the bins out"), "Reminder: put the bins out.")


class EngineTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.object(timers, "DATABASE", Path(folder) / "timers.db"))
        self.enterContext(patch.object(timers, "resolve_output", return_value=("assist_satellite.kitchen", "Kitchen")))
        self.now = SATURDAY_10AM.timestamp()
        self.enterContext(patch.object(timers, "time", side_effect=lambda: self.now))
        self.enterContext(patch.object(reminders, "datetime", Mock(now=Mock(return_value=SATURDAY_10AM),
                                                                     side_effect=datetime)))

    def say(self, phrase):
        self.assertTrue(timers.matches(phrase))
        return timers.handle_result(phrase, Mock(), satellite="assist_satellite.kitchen")

    def test_set_list_cancel(self):
        result = self.say("remind me in 20 minutes to check the oven")
        self.assertEqual((result.reply, result.outcome), ("I'll remind you in 20 minutes: check the oven.", Outcome.TIMER_SET))
        self.assertEqual(self.say("remind me at six to put the bins out").reply,
                         "I'll remind you at 18:00: put the bins out.")
        self.say("remind me at six to put the bins out")  # same reminder again: updated, not duplicated
        listing = self.say("what reminders do I have")
        self.assertEqual(listing.reply, "2 reminders: check the oven in 20 minutes; put the bins out at 18:00.")
        self.assertIs(listing.outcome, Outcome.TIMER_STATUS)
        self.assertEqual(self.say("cancel the bins reminder").reply, "Cancelled the reminder to put the bins out.")
        self.assertEqual(self.say("cancel my reminders").reply, "Cancelled 1 reminder.")
        self.assertIs(self.say("cancel my reminders").outcome, Outcome.NO_TIMER)

    def test_limits_and_unknown_times(self):
        self.assertIs(self.say("remind me at 25 to x").outcome, Outcome.UNRESOLVED)
        self.assertIn("a week ahead", self.say("remind me in 200 hours to x").reply)
        with patch.object(timers, "resolve_output", return_value=None):
            self.assertIs(self.say("remind me in 5 minutes to x").outcome, Outcome.UNAVAILABLE)

    def test_a_due_reminder_speaks_its_message_until_stopped_and_can_notify_phones(self):
        self.say("remind me in 5 minutes to check the oven")
        calls = []
        self.now += 6 * 60
        with patch.object(timers, "ha_json", side_effect=lambda opener, path, data=None, timeout=2: calls.append((path, data))), \
                patch.dict(os.environ, {"DECLAN_REMINDER_NOTIFY": "notify.mobile_app_jaco, not valid",
                                        "DECLAN_TIMER_ALARM_MEDIA_ID": "media-source://media_source/local/alarm.mp3"}):
            timers.ring_due(Mock())
            self.now += timers.ALARM_INTERVAL + 1
            timers.ring_due(Mock())
        announces = [data for path, data in calls if path.endswith("/announce")]
        self.assertEqual([data["message"] for data in announces], ["Reminder: check the oven."] * 2)
        self.assertNotIn("media_id", announces[0])  # no alarm sound before the message
        self.assertEqual([path for path, _ in calls if "notify" in path], ["/api/services/notify/mobile_app_jaco"])
        self.assertTrue(timers.matches("stop"))
        self.assertIs(timers.handle_result("stop", Mock(), satellite="assist_satellite.kitchen").outcome,
                      Outcome.TIMER_STOPPED)


if __name__ == "__main__":
    unittest.main()
