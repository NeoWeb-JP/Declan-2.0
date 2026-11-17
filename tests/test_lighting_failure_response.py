"""Lighting failure response extraction regression tests."""
import unittest
from unittest.mock import Mock
from response_composition import lighting_failure_reply


class LightingFailureReplyTests(unittest.TestCase):
    def setUp(self):
        self.category = Mock(return_value="lighting")
        self.parse = Mock()
        self.render = Mock(return_value="Editable failure response.")

    def reply(self, *, light=("Not found.", "unresolved"), routine=None,
              outcome="unresolved", phrase="turn off kitchen", guest=False):
        return lighting_failure_reply("Not found.", light_result=light,
            routine_turn=routine, outcome=outcome, phrase=phrase,
            response_guest=guest, response_category=self.category,
            parse_light_command=self.parse, render_failure=self.render)

    def test_unresolved_lighting_uses_editable_failure(self):
        self.assertEqual(self.reply(guest=True), "Editable failure response.")
        self.render.assert_called_once_with("lighting", "Not found.", guest=True)

    def test_confirmed_and_preview_outcomes_are_not_rewritten(self):
        self.assertEqual(self.reply(outcome="confirmed"), "Not found.")
        self.assertEqual(self.reply(outcome="preview"), "Not found.")
        self.render.assert_not_called()

    def test_preview_phrase_is_not_rewritten(self):
        self.assertEqual(self.reply(phrase="preview turn off kitchen"), "Not found.")
        self.assertEqual(self.reply(phrase="dry-run turn off kitchen"), "Not found.")
        self.render.assert_not_called()

    def test_routine_follow_on_not_rewritten(self):
        self.assertEqual(self.reply(routine=(("auto:script.test", {}), "turn off kitchen")), "Not found.")
        self.render.assert_not_called()

    def test_missing_lighting_result_not_rewritten(self):
        self.assertEqual(self.reply(light=None), "Not found.")
        self.render.assert_not_called()
