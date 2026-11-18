"""Device command dispatch and adaptation regression tests."""

import unittest
from unittest.mock import Mock

from device_response_orchestration import dispatch_device_response


def dependencies():
    names = (
        "registry_factory", "dependencies_factory", "context_factory",
        "parse_status", "describe_status", "connection", "inventory",
        "decorate", "guest_mode_entity", "parse_feedback", "feedback",
        "parse_control", "control", "parse_music", "play",
        "music_inventory", "areas", "search_media",
    )
    return {name: Mock() for name in names}


class DeviceResponseOrchestrationTests(unittest.TestCase):
    def test_forwards_device_context_and_adapts_result(self):
        dispatch = Mock(return_value="device")
        adapt = Mock(return_value="response")
        deps = dependencies()
        result = dispatch_device_response(
            "pause music", source="assist", last_device="speaker",
            origin_device="kitchen", satellite="sat",
            dispatch=dispatch, adapt=adapt, **deps,
        )
        self.assertEqual(result, "response")
        dispatch.assert_called_once_with(
            "pause music", source="assist", last_device="speaker",
            origin_device="kitchen", satellite="sat", **deps,
        )
        adapt.assert_called_once_with("device")

    def test_unmatched_device_falls_through_without_adaptation(self):
        adapt = Mock()
        result = dispatch_device_response(
            "turn on lights", source="chat", last_device=None,
            origin_device=None, satellite=None,
            dispatch=Mock(return_value=None), adapt=adapt,
            **dependencies(),
        )
        self.assertIsNone(result)
        adapt.assert_not_called()


if __name__ == "__main__":
    unittest.main()
