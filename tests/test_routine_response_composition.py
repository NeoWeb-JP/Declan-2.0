"""Custom routine reply composition regression tests."""
import unittest
from unittest.mock import Mock
from declan.turn.response_composition import routine_reply


class RoutineReplyTests(unittest.TestCase):
    def setUp(self):
        self.selection = (("auto:script.test", {"_declan_reply_category": "morning"}), None)
        self.render = Mock(return_value="Custom sass.")
        self.personality = Mock()
        self.personality.dinner_music_feedback.return_value = None

    def decorate(self, *, outcome="confirmed", phrase="good morning", selection=None,
                 voice=None, original="Routine started.", visitor=False, guest=False):
        return routine_reply("Routine started.", outcome=outcome,
            routine_turn=self.selection if selection is None else selection,
            routine_voice_result=voice, original_routine_reply=original,
            phrase=phrase, action_results=[], guest=guest,
            visitor_present=visitor, render=self.render, personality=self.personality)

    def test_custom_response_selected(self):
        self.assertEqual(self.decorate(), "Custom sass.")
        self.render.assert_called_once_with(self.selection[0], "confirmed",
                                            "Routine started.", guest=False)

    def test_chained_command_preserves_follow_on(self):
        selection = (self.selection[0], "turn off kitchen")
        result = self.decorate(selection=selection,
                               voice=("Routine started.", "confirmed"),
                               original="Routine started. Kitchen off.")
        self.assertEqual(result, "Custom sass. Kitchen off.")

    def test_preview_and_safety_are_not_decorated(self):
        self.assertEqual(self.decorate(outcome="preview"), "Routine started.")
        self.assertEqual(self.decorate(phrase="fire alarm"), "Routine started.")
        self.render.assert_not_called()

    def test_guest_or_unknown_visitor_uses_guest_lines(self):
        self.decorate(visitor=None)
        self.assertTrue(self.render.call_args.kwargs["guest"])

    def test_dinner_music_note_only_once(self):
        selection = (("auto:script.dinner", {"_declan_reply_category": "dinner"}), None)
        self.personality.dinner_music_feedback.return_value = "Music playing."
        self.render.return_value = "Dinner ready. Music playing."
        self.assertEqual(self.decorate(selection=selection), "Dinner ready. Music playing.")
