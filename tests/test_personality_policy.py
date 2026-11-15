"""Personality policy regression tests."""
from datetime import datetime
import unittest

import personality_policy as p


class PersonalityPolicyTests(unittest.TestCase):
    def test_savage_default_and_no_immediate_repeats(self):
        replies = [p.decorate("Kitchen lights are on.", visitor_present=False) for _ in range(4)]
        self.assertEqual(len(set(replies)), 4)
        self.assertTrue(all(x.startswith("Kitchen lights are on.") for x in replies))

    def test_guest_and_visitors_do_not_get_home_roasts(self):
        for options in ({"guest": True, "visitor_present": False},
                        {"visitor_present": True}, {}):
            reply = p.decorate("Done.", **options)
            self.assertTrue(any(x in reply for x in p._GUEST))

    def test_failures_and_safety_are_never_decorated(self):
        for outcome in p._SAFE_OUTCOMES:
            self.assertEqual(p.decorate("Could not connect.", outcome=outcome,
                                        visitor_present=False), "Could not connect.")
        self.assertEqual(p.decorate("Smoke detected.", safety=True,
                                    visitor_present=False), "Smoke detected.")

    def test_night_boundaries_and_volume(self):
        def at(hour, minute=0):
            return datetime(2026, 11, 15, hour, minute)
        self.assertTrue(p.quiet_hours(at(23)))
        self.assertTrue(p.quiet_hours(at(6, 59)))
        self.assertFalse(p.quiet_hours(at(7)))
        self.assertAlmostEqual(p.speech_volume(.6, now=at(23)), .12)
        self.assertEqual(p.speech_volume(.6, now=at(7)), .6)

    def test_overnight_safety_only(self):
        at = datetime(2026, 11, 15, 23, 30)
        self.assertFalse(p.overnight_announcement_allowed("ev_reminder", now=at))
        self.assertTrue(p.overnight_announcement_allowed("smoke", now=at))

    def test_edd_speech_only(self):
        self.assertEqual(p.tts_spelling("Edd and Edward"), "Ed and Edward")


if __name__ == "__main__":
    unittest.main()
