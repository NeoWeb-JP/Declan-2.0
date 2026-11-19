"""Regression coverage for extracted voice-turn command dispatch."""
import unittest

from service_doubles import patch_module_collaborators
from types import SimpleNamespace
from unittest.mock import Mock

from declan.turn import turn_dispatch_orchestration
from declan.core.execution_results import Outcome


class TurnDispatchExtractionTests(unittest.TestCase):
    def setUp(self):
        self.r = Mock()
        patch_module_collaborators(self, turn_dispatch_orchestration, self.r)
        self.r.build_opener.return_value = object()
        self.r.turn_preview_stage.resolve.return_value = None
        self.r.turn_direct_dispatch.dispatch.return_value = None
        self.r.turn_routine_stage.dispatch.return_value = None
        self.r.turn_fallback_dispatch.dispatch.return_value = None
        self.r.configured_guest_mode_entity.return_value = "guest"

    def dispatch(self):
        return turn_dispatch_orchestration.dispatch(
            "play country", source="voice", origin_device="kitchen",
            satellite="kitchen", action_results=Mock(), scope="home",
            last_lights=None, last_device=None, last_information=None,
            services=self.r,
        )

    def test_preview_short_circuits_later_dispatch(self):
        self.r.turn_preview_stage.resolve.return_value = SimpleNamespace(reply="preview", outcome=Outcome.PREVIEW)
        result = self.dispatch()
        self.assertEqual((result.reply, result.outcome), ("preview", Outcome.PREVIEW))
        self.r.turn_direct_dispatch.dispatch.assert_not_called()
        self.r.turn_routine_stage.dispatch.assert_not_called()
        self.r.turn_fallback_dispatch.dispatch.assert_not_called()

    def test_direct_dispatch_short_circuits_routine(self):
        self.r.turn_direct_dispatch.dispatch.return_value = SimpleNamespace(
            reply="stopped", outcome=Outcome.CONFIRMED, routine_status="done")
        result = self.dispatch()
        self.assertEqual((result.reply, result.routine_status), ("stopped", "done"))
        self.r.turn_routine_stage.dispatch.assert_not_called()
        self.r.turn_fallback_dispatch.dispatch.assert_not_called()

    def test_routine_dispatch_preserves_voice_and_lighting_context(self):
        self.r.turn_routine_stage.dispatch.return_value = SimpleNamespace(
            reply="playing", outcome=Outcome.STARTED, routine_status="done",
            routine_turn="routine", routine_voice_result="voice", lighting_context="lights")
        result = self.dispatch()
        self.assertEqual((result.routine_turn, result.routine_voice_result, result.lighting_context),
                         ("routine", "voice", "lights"))
        self.r.turn_fallback_dispatch.dispatch.assert_not_called()

    def test_fallback_dispatch_preserves_all_context(self):
        self.r.turn_fallback_dispatch.dispatch.return_value = SimpleNamespace(
            reply="fallback", outcome=Outcome.CONFIRMED, information_context="info",
            status_target="target", lighting_context="lights", light_result="light")
        result = self.dispatch()
        self.assertEqual((result.reply, result.information_context, result.status_target,
                          result.lighting_context, result.light_result),
                         ("fallback", "info", "target", "lights", "light"))

    def test_no_match_has_empty_outcome(self):
        result = self.dispatch()
        self.assertIsNone(result.reply)
        self.assertIsNone(result.outcome)
        self.assertIsNone(result.light_result)


if __name__ == "__main__":
    unittest.main()
