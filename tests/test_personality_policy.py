"""Personality policy regression tests."""
from datetime import datetime
import unittest

import personality_policy as p
import household_language


class PersonalityPolicyTests(unittest.TestCase):
    def test_sexy_start_and_end_replies_vary_without_claiming_playback_or_completion(self):
        for action in ("start", "end"):
            replies = [p.sexy_request_reply(action, visitor_present=False) for _ in range(4)]
            self.assertEqual(len(set(replies)), 4)
            for reply in replies:
                self.assertIn(reply, tuple(map(household_language.render, p._SEXY_HOME[action])))
                self.assertNotIn("Bedroom mood requested", reply)
                self.assertNotIn("Bedroom reset requested", reply)
                self.assertNotIn("is playing", reply)
                self.assertNotIn("completed", reply)

    def test_sexy_guest_and_unknown_visitor_replies_remain_private(self):
        for options in ({"guest": True}, {"visitor_present": True}, {"visitor_present": None}):
            for action in ("start", "end"):
                replies = [p.sexy_request_reply(action, **options) for _ in range(4)]
                self.assertEqual(len(set(replies)), 4)
                for reply in replies:
                    self.assertIn(reply, tuple(map(household_language.render, p._SEXY_GUEST[action])))
                    self.assertNotIn("Bedroom mood requested", reply)
                    self.assertNotIn("Bedroom reset requested", reply)
                    self.assertFalse(any(name in reply for name in ("Jaco", "Edd", "Finn", "Tux")))
                    self.assertFalse(any(word in reply.lower() for word in ("safeword", "restraints", "handcuff", "whips")))

    def test_night_acknowledgements_are_varied_without_duplicate_sorted_or_success_claims(self):
        replies = [p.night_request_reply(visitor_present=False) for _ in range(4)]
        self.assertEqual(len(set(replies)), 4)
        for reply in replies:
            self.assertTrue(reply.startswith("Good night. "))
            self.assertIn(reply.removeprefix("Good night. "), tuple(map(household_language.render, p._NIGHT_HOME)))
            self.assertNotIn("Sorted", reply)
            self.assertNotIn("completed", reply)
            self.assertNotIn("lights are off", reply)

    def test_night_guest_and_unknown_presence_keep_household_details_private(self):
        for options in ({"guest": True, "visitor_present": False}, {"visitor_present": True},
                        {"visitor_present": None}):
            replies = [p.night_request_reply(**options) for _ in range(4)]
            self.assertEqual(len(set(replies)), 4)
            for reply in replies:
                self.assertIn(reply.removeprefix("Good night. "), tuple(map(household_language.render, p._NIGHT_GUEST)))
                self.assertFalse(any(name in reply for name in ("Jaco", "Edd", "Finn", "Tux")))

    def test_morning_acknowledgements_are_varied_and_do_not_claim_device_success(self):
        replies = [p.morning_request_reply(visitor_present=False) for _ in range(4)]
        self.assertEqual(len(set(replies)), 4)
        for reply in replies:
            self.assertTrue(reply.startswith("Good morning. "))
            self.assertIn(reply.removeprefix("Good morning. "), tuple(map(household_language.render, p._MORNING_HOME)))
            self.assertNotIn("completed", reply)
            self.assertNotIn("lights are", reply)

    def test_morning_guest_and_unknown_presence_replies_keep_household_details_private(self):
        for options in ({"guest": True, "visitor_present": False}, {"visitor_present": True},
                        {"visitor_present": None}):
            replies = [p.morning_request_reply(**options) for _ in range(4)]
            self.assertEqual(len(set(replies)), 4)
            for reply in replies:
                self.assertIn(reply.removeprefix("Good morning. "), tuple(map(household_language.render, p._MORNING_GUEST)))
                self.assertFalse(any(name in reply for name in ("Jaco", "Edd", "Finn", "Tux")))

    def test_movie_requests_vary_for_each_direction_without_claiming_completion(self):
        for action, prefix in (("start", "Movie setup requested."), ("end", "Movie shutdown requested."),
                               ("toggle", "Movie Time requested.")):
            replies = [p.movie_request_reply(action, visitor_present=False) for _ in range(4)]
            self.assertEqual(len(set(replies)), 4)
            for reply in replies:
                self.assertTrue(reply.startswith(prefix))
                self.assertIn(reply.removeprefix(prefix + " "), p._MOVIE_HOME[action])
                self.assertNotIn("completed", reply)
                self.assertNotRegex(reply, r"\baudit\b")

    def test_movie_guest_and_unknown_visitor_fallbacks_are_playful_and_private(self):
        for options in ({"guest": True, "visitor_present": False}, {"visitor_present": True},
                        {"visitor_present": None}):
            for action in ("start", "end", "toggle"):
                replies = [p.movie_request_reply(action, **options) for _ in range(4)]
                self.assertEqual(len(set(replies)), 4)
                for reply in replies:
                    self.assertTrue(any(reply.endswith(line) for line in p._MOVIE_GUEST[action]))
                    self.assertFalse(any(name in reply for name in ("Jaco", "Edd", "Finn", "Tux")))
                    self.assertNotIn("record the result", reply)

    def test_unknown_movie_direction_uses_direction_neutral_lines(self):
        reply = p.movie_request_reply("future_action", visitor_present=False)
        self.assertTrue(reply.startswith("Movie Time requested."))
        self.assertTrue(any(reply.endswith(line) for line in p._MOVIE_HOME["toggle"]))

    def test_savage_default_and_no_immediate_repeats(self):
        replies = [p.decorate("Kitchen lights are on.", visitor_present=False) for _ in range(4)]
        self.assertEqual(len(set(replies)), 4)
        self.assertTrue(all(x.startswith("Kitchen lights are on.") for x in replies))

    def test_dinner_is_its_own_varied_reply_without_generic_completion_prefix(self):
        replies = [p.decorate("", category="dinner", visitor_present=False) for _ in range(4)]
        self.assertEqual(len(set(replies)), 4)
        self.assertTrue(all(reply in tuple(map(household_language.render, p._DINNER_HOME)) for reply in replies))
        self.assertTrue(all("Routine finished" not in reply and "Sorted." not in reply for reply in replies))
        self.assertEqual(p.decorate(replies[0], category="general", visitor_present=False), replies[0])

    def test_dinner_guest_lines_are_still_food_specific_and_privacy_safe(self):
        for options in ({"guest": True}, {"visitor_present": True}, {"visitor_present": None}):
            reply = p.decorate("", category="dinner", **options)
            self.assertIn(reply, tuple(map(household_language.render, p._DINNER_GUEST)))
            self.assertFalse(any(name in reply for name in ("Jaco", "Edd", "Finn", "Tux")))

    def test_dinner_sass_never_masks_failed_or_unverified_actions(self):
        for outcome in ("failed", "partial", "unverified", "started", "cancelled"):
            self.assertEqual(p.decorate("Dinner could not be confirmed.", category="dinner", outcome=outcome),
                             "Dinner could not be confirmed.")

    def test_optional_dinner_music_is_reported_as_requested_not_playing(self):
        step = {"target": "dinner_music", "action": "request_playback", "required": False, "status": "requested"}
        note = p.dinner_music_feedback([step], visitor_present=False)
        self.assertIn("requested the music", note)
        self.assertIn("Spotify", note)
        self.assertNotIn("is playing", note)
        self.assertEqual(p.dinner_music_feedback([]), "")
        self.assertEqual(p.dinner_music_feedback([{**step, "required": True}]), "")
        failed = p.dinner_music_feedback([{**step, "status": "not_configured"}])
        self.assertIn("couldn't confirm", failed)
        self.assertNotIn("requested the music", failed)
        guest = p.dinner_music_feedback([step], guest=True)
        self.assertNotIn("bloody", guest)

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

