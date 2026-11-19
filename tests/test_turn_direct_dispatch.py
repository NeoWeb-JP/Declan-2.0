"""Stop commands take precedence over guest/roast commands."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from declan.turn import turn_direct_dispatch as direct


class DirectDispatchTests(unittest.TestCase):
    def setUp(self):
        self.kwargs = dict(
            source="assist", origin_device="device", satellite="sat",
            stop_registry=lambda: None, context_factory=object(),
            stop_routines=object(), stop_everywhere=object(),
            connection=object(), roast_target=object(),
            respond_to_roast=object(), guest_mode=object(),
            visitors_present=object(), response_guest_mode=object(),
            roast_respond=object(), assignment_action=object(),
            guest_commands={}, guest_assignment=object(),
        )

    def test_stop_short_circuits_guest_dispatch(self):
        stop = object()
        result = SimpleNamespace(result=SimpleNamespace(reply="stopped", outcome="confirmed"), routine_status="stopped")
        with patch.object(direct.stop_command_dispatch, "dispatch_stop", return_value=stop), patch.object(
            direct.stop_result_response, "stop_response", return_value=result,
        ), patch.object(direct.roast_guest_dispatch, "dispatch_roast_or_guest_result") as guest:
            response = direct.dispatch("stop", **self.kwargs)
        guest.assert_not_called()
        self.assertEqual((response.reply, response.outcome, response.routine_status), ("stopped", "confirmed", "stopped"))

    def test_guest_follows_unmatched_stop(self):
        with patch.object(direct.stop_command_dispatch, "dispatch_stop", return_value=None), patch.object(
            direct.roast_guest_dispatch, "dispatch_roast_or_guest_result",
            return_value=SimpleNamespace(reply="welcome", outcome="confirmed"),
        ):
            result = direct.dispatch("guests are in charge", **self.kwargs)
        self.assertEqual(result.reply, "welcome")
        self.assertIsNone(result.routine_status)

    def test_no_match_allows_routine_dispatch(self):
        with patch.object(direct.stop_command_dispatch, "dispatch_stop", return_value=None), patch.object(
            direct.roast_guest_dispatch, "dispatch_roast_or_guest_result", return_value=None,
        ):
            self.assertIsNone(direct.dispatch("good morning", **self.kwargs))


if __name__ == "__main__":
    unittest.main()
