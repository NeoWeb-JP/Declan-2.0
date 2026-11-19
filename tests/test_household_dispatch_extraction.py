"""Compatibility regression tests for extracted household routine dispatch."""
import unittest
from unittest.mock import patch

import server
import household_routine_dispatch as dispatch


class HouseholdDispatchExtractionTests(unittest.TestCase):
    def test_dinner_wrapper_preserves_patched_dependencies(self):
        with patch.object(dispatch, "start_dinner_result", return_value="sentinel") as extracted:
            self.assertEqual(server.start_dinner_result(None, approved=True), "sentinel")
        kwargs = extracted.call_args.kwargs
        self.assertTrue(kwargs["approved"])
        self.assertIs(kwargs["policy"], server.personality_policy)
        self.assertIs(kwargs["registry"], server.routine_registry)
        self.assertIs(kwargs["choose_response"], server.choose_line)
        self.assertIs(kwargs["guest_mode"], server.read_guest_mode)
        self.assertIs(kwargs["request_factory"], server.Request)

    def test_guest_wrapper_preserves_patched_dependencies(self):
        with patch.object(dispatch, "guest_assignment_result", return_value="sentinel") as extracted:
            self.assertEqual(server.guest_assignment_result("clear", None), "sentinel")
        kwargs = extracted.call_args.kwargs
        self.assertIs(kwargs["entities"], server.household_entities)
        self.assertIs(kwargs["sass"], server.add_sass)
        self.assertIs(kwargs["request_factory"], server.Request)

    def test_unconfigured_guest_connection_does_not_dispatch(self):
        result = server.guest_assignment_result("clear", None)
        self.assertEqual(result.outcome.value, "unavailable")

    def test_unconfigured_dinner_connection_does_not_dispatch_when_allowed(self):
        with patch.object(server.personality_policy, "overnight_announcement_allowed", return_value=True):
            result = server.start_dinner_result(None)
        self.assertEqual(result.outcome.value, "not_configured")


if __name__ == "__main__":
    unittest.main()
