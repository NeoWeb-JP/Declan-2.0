"""Roast and guest dispatch forwarding regressions."""

import unittest
from unittest.mock import Mock

from roast_guest_orchestration import dispatch_roast_guest


class RoastGuestOrchestrationTests(unittest.TestCase):
    def test_dispatch_forwards_dependencies_and_result(self):
        dispatch = Mock(return_value="guest-result")
        dependencies = {
            name: Mock() for name in (
                "roast_target", "respond_to_roast", "guest_mode",
                "visitors_present", "response_guest_mode", "roast_respond",
                "assignment_action", "guest_assignment", "connection",
            )
        }
        dependencies["guest_commands"] = {"guests are leaving"}
        result = dispatch_roast_guest("guests are leaving", dispatch=dispatch, **dependencies)
        self.assertEqual(result, "guest-result")
        dispatch.assert_called_once_with("guests are leaving", **dependencies)

    def test_unmatched_command_returns_none(self):
        dispatch = Mock(return_value=None)
        dependencies = {
            name: Mock() for name in (
                "roast_target", "respond_to_roast", "guest_mode",
                "visitors_present", "response_guest_mode", "roast_respond",
                "assignment_action", "guest_assignment", "connection",
            )
        }
        dependencies["guest_commands"] = set()
        self.assertIsNone(dispatch_roast_guest("lights on", dispatch=dispatch, **dependencies))


if __name__ == "__main__":
    unittest.main()
