"""Grouped information/device/lighting dispatch precedence tests."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import turn_fallback_dispatch as stage


class FallbackDispatchTests(unittest.TestCase):
    def setUp(self):
        empty = SimpleNamespace(**{name: None for name in (
            'matches', 'follow_up', 'handle_result', 'question_context',
            'parse', 'describe_result', 'parse_feedback', 'feedback_result',
            'parse_control', 'control_result', 'play_result',
            'dispatch_lighting', 'confirmed_lighting_context',
        )})
        self.args = ("test", "assist", None, None, None, None, None, [], None, None, None)
        self.kwargs = dict(
            command_registry=SimpleNamespace(information_registry=None, RequestContext=None, registry=None, Dependencies=None, lighting_registry=None),
            conditions=empty, add_sass=None, read_guest_mode=None,
            device_status=empty, ha_device_connection=None,
            read_ha_inventory_result=None, GUEST_MODE_ENTITY=None,
            music=empty, read_music_inventory_result=None,
            read_ha_areas=None, search_media_result=None,
            lighting_intents=empty, parse_light_command=None,
            handle_light_request_result=None, lighting_command_dispatch=empty,
            lighting_context_finalization=empty,
        )

    def test_information_preempts_device_and_lighting(self):
        info = SimpleNamespace(result=SimpleNamespace(reply="answer", outcome="confirmed"), information_context="context")
        with patch.object(stage.information_command_dispatch, "dispatch_information", return_value=object()), patch.object(
            stage.information_result_response, "information_response", return_value=info
        ), patch.object(stage.device_command_dispatch, "dispatch_device") as device, patch.object(
            stage.lighting_result_dispatch, "dispatch_lighting_response"
        ) as lights:
            result = stage.dispatch(*self.args, **self.kwargs)
        self.assertEqual((result.reply, result.information_context), ("answer", "context"))
        device.assert_not_called()
        lights.assert_not_called()

    def test_device_preempts_lighting(self):
        device_response = SimpleNamespace(result=SimpleNamespace(reply="device", outcome="confirmed"), status_target="speaker")
        with patch.object(stage.information_command_dispatch, "dispatch_information", return_value=None), patch.object(
            stage.device_command_dispatch, "dispatch_device", return_value=object()
        ), patch.object(stage.device_result_response, "device_response", return_value=device_response), patch.object(
            stage.lighting_result_dispatch, "dispatch_lighting_response"
        ) as lights:
            result = stage.dispatch(*self.args, **self.kwargs)
        self.assertEqual((result.reply, result.status_target), ("device", "speaker"))
        lights.assert_not_called()

    def test_no_match_falls_through(self):
        with patch.object(stage.information_command_dispatch, "dispatch_information", return_value=None), patch.object(
            stage.device_command_dispatch, "dispatch_device", return_value=None
        ), patch.object(stage.lighting_result_dispatch, "dispatch_lighting_response", return_value=None):
            self.assertIsNone(stage.dispatch(*self.args, **self.kwargs))


if __name__ == "__main__":
    unittest.main()
