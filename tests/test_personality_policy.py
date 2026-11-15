"""Personality policy regression tests."""
from datetime import datetime
import unittest

import personality_policy as p


class PersonalityPolicyTests(unittest.TestCase):
    def test_savage_default_and_no_immediate_repeats(self):
        replies = [p.decorate("Kitchen lights are on.", visitor_present=False) for _ in range(4)]
        self.assertEqual(len(set(replies)), 4)
        self.assertTrue(all(x.startswith("Kitchen lights are on.") for x in replies))

    def test_decoration_is_idempotent_across_categories_and_modes(self):
        home = p.decorate("Lights on.", visitor_present=False)
        self.assertEqual(p.decorate(home, visitor_present=False, category="music"), home)
        self.assertEqual(p.decorate(home, guest=True, visitor_present=True), home)
        guest = p.decorate("All done.", guest=True)
        self.assertEqual(p.decorate(guest, visitor_present=False), guest)

    def test_guest_mode_authority_and_visitor_presence_are_independent(self):
        self.assertEqual(p.response_guest_mode("on", False), "on")
        self.assertEqual(p.response_guest_mode("on", None), "on")
        self.assertEqual(p.response_guest_mode("off", True), "on")
        self.assertEqual(p.response_guest_mode("off", None), "on")
        self.assertEqual(p.response_guest_mode("off", False), "off")

    def test_guest_and_visitors_do_not_get_home_roasts(self):
        for options in ({"guest": True, "visitor_present": False},
                        {"visitor_present": True}, {"visitor_present": None}):
            reply = p.decorate("Done.", **options)
            self.assertTrue(any(x in reply for x in p._GUEST))

    def test_failures_and_safety_are_never_decorated(self):
        for outcome in p._SAFE_OUTCOMES:
            self.assertEqual(p.decorate("Could not connect.", outcome=outcome,
                                        visitor_present=False), "Could not connect.")
        self.assertEqual(p.decorate("Smoke detected.", safety=True,
                                    visitor_present=False), "Smoke detected.")
        for outcome in (None, "", "pending", "timeout", "partially_completed", "future_error"):
            self.assertEqual(p.decorate("Uncertain outcome.", outcome=outcome,
                                        visitor_present=False), "Uncertain outcome.")
        self.assertNotEqual(p.decorate("Completed.", outcome="confirmed",
                                       visitor_present=False), "Completed.")

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

    def test_overnight_announcement_categories(self):
        at = datetime(2026, 11, 15, 23, 15)
        for kind in ("security", "smoke", "carbon_monoxide", "critical_safety"):
            self.assertTrue(p.overnight_announcement_allowed(kind, now=at))
        for kind in ("dinner", "ev_reminder", "music", "routine"):
            self.assertFalse(p.overnight_announcement_allowed(kind, now=at))
        self.assertTrue(p.overnight_announcement_allowed(
            "dinner", now=datetime(2026, 11, 15, 12)))

    def test_edd_speech_only(self):
        self.assertEqual(p.tts_spelling("Edd and Edward"), "Ed and Edward")


if __name__ == "__main__":
    unittest.main()
