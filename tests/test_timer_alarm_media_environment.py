"""Verify timer alarm media environment selection and fallback."""
import os
import unittest
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import timers


class TimerAlarmMediaEnvironmentTests(unittest.TestCase):
    def ring(self, settings, *, media_error=False):
        timer = {"id": 1, "name": "Tea", "satellite": "assist_satellite.kitchen",
                 "deadline": 100.0, "next_alarm": 100.0}
        db = MagicMock()
        first = MagicMock()
        first.fetchone.return_value = timer
        claimed = MagicMock()
        claimed.rowcount = 1
        exists = MagicMock()
        exists.fetchone.return_value = (1,)
        db.execute.side_effect = [first, claimed, exists, MagicMock()]
        calls = []

        def fake_ha(_opener, path, *, data=None, timeout=None):
            calls.append((path, data, timeout))
            if media_error and data is not None and "media_id" in data:
                raise ValueError("unavailable media")
            return {}

        with patch.dict(os.environ, settings, clear=True), patch.object(
                timers, "database", side_effect=lambda: nullcontext(db)), patch.object(
                timers, "time", return_value=101.0), patch.object(
                timers, "ha_json", side_effect=fake_ha):
            timers.ring_due(object())
        return calls, db

    def test_unset_empty_and_blank_use_spoken_alarm(self):
        for settings in ({}, {"DECLAN_TIMER_ALARM_MEDIA_ID": ""}, {
                "DECLAN_TIMER_ALARM_MEDIA_ID": "  "}):
            with self.subTest(settings=settings):
                calls, _ = self.ring(settings)
                self.assertEqual(len(calls), 1)
                self.assertNotIn("media_id", calls[0][1])
                self.assertTrue(calls[0][1]["preannounce"])

    def test_valid_media_source_is_trimmed_and_announced(self):
        media = "media-source://media_source/local/chime.mp3"
        calls, _ = self.ring({"DECLAN_TIMER_ALARM_MEDIA_ID": "  " + media + "  "})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]["media_id"], media)
        self.assertFalse(calls[0][1]["preannounce"])

    def test_invalid_scheme_falls_back_to_spoken_alarm(self):
        calls, _ = self.ring({"DECLAN_TIMER_ALARM_MEDIA_ID": "https://example.com/chime.mp3"})
        self.assertEqual(len(calls), 1)
        self.assertNotIn("media_id", calls[0][1])

    def test_rejected_media_source_falls_back_to_spoken_alarm(self):
        calls, _ = self.ring({
            "DECLAN_TIMER_ALARM_MEDIA_ID": "media-source://media_source/local/missing.mp3"
        }, media_error=True)
        self.assertEqual(len(calls), 2)
        self.assertIn("media_id", calls[0][1])
        self.assertNotIn("media_id", calls[1][1])


if __name__ == "__main__":
    unittest.main()
