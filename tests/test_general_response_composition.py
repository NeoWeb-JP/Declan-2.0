"""General response composition regression tests."""
import unittest
from unittest.mock import Mock
from response_composition import general_reply
from execution_results import Outcome


class GeneralReplyTests(unittest.TestCase):
    def test_typed_and_legacy_outcomes_have_identical_decoration_gates(self):
        for outcome in Outcome:
            with self.subTest(outcome=outcome):
                self.personality.reset_mock()
                legacy = self.reply(outcome=outcome.value)
                legacy_calls = self.personality.mock_calls
                self.personality.reset_mock()
                self.assertEqual(self.reply(outcome=outcome), legacy)
                self.assertEqual(self.personality.mock_calls, legacy_calls)
        for outcome in ("future_outcome", [], None):
            self.personality.reset_mock()
            self.assertEqual(self.reply(outcome=outcome), "Routine done.")
            self.personality.decorate.assert_not_called()

    def setUp(self):
        self.personality = Mock()
        self.personality.decorate.return_value = "Sassy reply."
        for name in ("_SAVAGE", "_GUEST", "_DINNER_HOME", "_DINNER_GUEST"):
            setattr(self.personality, name, ())
        self.personality.dinner_music_feedback.return_value = None
        self.music = Mock(return_value=None)
        self.control = Mock(return_value=None)

    def reply(self, *, outcome="reported_success", phrase="good morning", text="Routine done.",
              turn=None, actions=None, light=None):
        if turn is None:
            turn = (("auto:script.test", {"_declan_reply_category": "morning"}), None)
        return general_reply(text, outcome=outcome, routine_reply="Routine done.",
            routine_turn=turn, light_result=light, phrase=phrase,
            action_results=[] if actions is None else actions,
            guest=False, visitor_present=False, personality=self.personality,
            lines={"home": (("Already sassy.",),)}, parse_music=self.music,
            parse_music_control=self.control)

    def test_verified_routine_decorated_once(self):
        self.assertEqual(self.reply(), "Sassy reply.")
        self.assertEqual(self.personality.decorate.call_args.args, ("Sorted.",))

    def test_unverified_request_not_decorated(self):
        self.assertEqual(self.reply(outcome="requested"), "Routine done.")
        self.personality.decorate.assert_not_called()

    def test_existing_sass_not_duplicated(self):
        self.assertEqual(self.reply(text="Already sassy."), "Already sassy.")
        self.personality.decorate.assert_not_called()

    def test_emergency_and_preview_bypass(self):
        self.assertEqual(self.reply(phrase="fire alarm"), "Routine done.")
        self.assertEqual(self.reply(phrase="preview good morning"), "Routine done.")
        self.personality.decorate.assert_not_called()

    def test_dinner_music_note(self):
        self.personality.dinner_music_feedback.return_value = "Music playing."
        turn = (("auto:script.dinner", {"_declan_reply_category": "dinner"}), None)
        self.assertEqual(self.reply(turn=turn), "Sassy reply. Music playing.")
        self.assertEqual(self.personality.decorate.call_args.kwargs["category"], "dinner")

    def test_light_result_does_not_get_general_sass(self):
        self.assertEqual(self.reply(light=("Done.", "confirmed")), "Routine done.")
        self.personality.decorate.assert_not_called()
