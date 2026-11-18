"""Regression coverage for the final command-dispatch stages."""

import unittest
from unittest.mock import Mock

from final_dispatch_orchestration import (
    dispatch_lighting, resolve_fallback, resolve_persona,
)


class FinalDispatchOrchestrationTests(unittest.TestCase):
    def test_lighting_forwards_context_and_evidence(self):
        dispatch = Mock(return_value="lighting-result")
        deps = {name: Mock() for name in (
            "registry_factory", "context_factory", "matches",
            "parse_light_command", "handle_light_request",
            "dispatch_lighting_command", "confirmed_lighting_context",
        )}
        result = dispatch_lighting(
            "lights on", source="assist", origin_device="lounge",
            satellite="sat", action_results="actions",
            last_lights="previous", scope="room", dispatch=dispatch, **deps,
        )
        self.assertEqual(result, "lighting-result")
        expected = dict(deps)
        expected["dispatch_lighting"] = expected.pop("dispatch_lighting_command")
        dispatch.assert_called_once_with(
            "lights on", source="assist", origin_device="lounge",
            satellite="sat", action_results="actions", last_lights="previous",
            scope="room", **expected,
        )

    def test_lighting_unmatched_returns_none(self):
        deps = {name: Mock() for name in (
            "registry_factory", "context_factory", "matches",
            "parse_light_command", "handle_light_request",
            "dispatch_lighting_command", "confirmed_lighting_context",
        )}
        self.assertIsNone(dispatch_lighting(
            "unknown", source="chat", origin_device=None, satellite=None,
            action_results=None, last_lights=None, scope=None,
            dispatch=Mock(return_value=None), **deps,
        ))

    def test_fallback_forwards_authorization_and_exposure_guard(self):
        resolve = Mock(return_value="fallback")
        deps = {name: Mock() for name in (
            "exposed_entities", "dispatch_fallback", "fallback_handler",
        )}
        result = resolve_fallback(
            "unknown", routine_reply=None, light_result=None,
            body={"message": "unknown"}, authorization="Bearer token",
            bridge_token="secret", source="assist", action_results="actions",
            resolve=resolve, **deps,
        )
        self.assertEqual(result, "fallback")
        resolve.assert_called_once_with(
            "unknown", routine_reply=None, light_result=None,
            body={"message": "unknown"}, authorization="Bearer token",
            bridge_token="secret", source="assist", action_results="actions",
            **deps,
        )

    def test_persona_preserves_three_part_result(self):
        resolve = Mock(return_value=(True, False, "guest"))
        guest_mode, visitors_present, personality = Mock(), Mock(), Mock()
        self.assertEqual(resolve_persona(
            resolve=resolve, guest_mode=guest_mode,
            visitors_present=visitors_present, personality=personality,
        ), (True, False, "guest"))
        resolve.assert_called_once_with(guest_mode, visitors_present, personality)


if __name__ == "__main__":
    unittest.main()
