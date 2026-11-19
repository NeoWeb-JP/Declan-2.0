"""Regression tests for extracted household and routine selection boundaries."""
import unittest
from unittest.mock import Mock

import household_selection_boundaries as boundaries


class HouseholdSelectionBoundaryTests(unittest.TestCase):
    def test_guest_mode_preserves_live_transport_dependencies(self):
        r = Mock()
        r.os.environ = {"HA_URL": "http://example.invalid"}
        boundaries.read_guest_mode(r=r)
        kwargs = r.ha_household_status.read_guest_mode.call_args.kwargs
        self.assertIs(kwargs["entities"], r.household_entities)
        self.assertIs(kwargs["request_factory"], r.Request)
        self.assertIs(kwargs["environ"], r.os.environ)

    def test_selection_preserves_live_discovery_and_phrase_dependencies(self):
        r = Mock()
        boundaries.select_routine_result("good morning", "kitchen", r=r)
        kwargs = r.routine_request_selection.select_routine_result.call_args.kwargs
        self.assertIs(kwargs["connect"], r.ha_device_connection)
        self.assertIs(kwargs["movie_parser"], r.parse_movie_request)
        self.assertIs(kwargs["morning_phrases"], r.GOOD_MORNING_PHRASES)

    def test_turn_selection_uses_live_server_callback(self):
        r = Mock()
        boundaries.select_routine_turn_result("movie time", "lounge", r=r)
        kwargs = r.routine_turn_orchestration.select_routine_turn_result.call_args.kwargs
        self.assertIs(kwargs["select"], r.select_routine_result)
        self.assertIs(kwargs["parse_movie"], r.parse_movie_request)

    def test_execution_forwards_approval_and_evidence(self):
        r = Mock()
        evidence = []
        boundaries.execute_routine_result("movie", evidence, approved=True, r=r)
        args = r.routine_turn_orchestration.execute_routine_result.call_args
        self.assertEqual(args.args, ("movie", evidence))
        self.assertTrue(args.kwargs["approved"])
        self.assertIs(args.kwargs["connect"], r.ha_device_connection)


if __name__ == "__main__":
    unittest.main()
