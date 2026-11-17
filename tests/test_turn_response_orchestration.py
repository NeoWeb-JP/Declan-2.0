"""Spoken response orchestration precedence regression tests."""
import unittest
from unittest.mock import Mock
from turn_response_orchestration import compose


class ResponseOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.composition = Mock()
        self.composition.general_reply.side_effect = self._stage("general")
        self.composition.routine_reply.side_effect = self._stage("routine")
        self.composition.lighting_failure_reply.side_effect = self._stage("lighting")
        self.composition.background_reply.return_value = None

    def _stage(self, name):
        def apply(reply, **kwargs):
            self.events.append((name, reply))
            return reply + ">" + name
        return apply

    def compose(self):
        return compose("original", outcome="confirmed", routine_reply="done",
            routine_turn=None, light_result=None, phrase="turn on light",
            action_results=[], guest=False, response_guest=False,
            visitor_present=False, routine_voice_result=None,
            personality=Mock(), lines={}, parse_music=Mock(),
            parse_music_control=Mock(), render_routine=Mock(),
            response_category=Mock(), parse_light_command=Mock(),
            render_failure=Mock(), composition=self.composition)

    def test_composition_order_is_general_routine_lighting(self):
        self.assertEqual(self.compose(), "original>general>routine>lighting")
        self.assertEqual([event[0] for event in self.events],
                         ["general", "routine", "lighting"])

    def test_background_reply_overrides_general_before_routine(self):
        self.composition.background_reply.return_value = "background"
        self.assertEqual(self.compose(), "background>routine>lighting")
        self.assertEqual(self.events[1], ("routine", "background"))

    def test_guest_context_passes_to_each_stage(self):
        self.compose()
        self.assertFalse(self.composition.general_reply.call_args.kwargs["guest"])
        self.assertFalse(self.composition.lighting_failure_reply.call_args.kwargs["response_guest"])

    def test_background_is_consulted_after_general(self):
        self.compose()
        self.composition.background_reply.assert_called_once()
        self.assertEqual(self.events[0][0], "general")

    def test_lighting_receives_routine_composed_text(self):
        self.compose()
        self.assertEqual(self.events[-1][1], "original>general>routine")
