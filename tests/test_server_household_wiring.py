"""Server-level wiring for household status and routine selection boundaries."""
from typing import Any
import unittest
from unittest.mock import patch

import server


class ServerHouseholdWiringTests(unittest.TestCase):
    def test_guest_mode_preserves_live_transport_dependencies(self):
        with patch.object(server.ha_household_status, "read_guest_mode") as read:
            server.read_guest_mode()
        kwargs = read.call_args.kwargs
        self.assertIs(kwargs["entities"], server.household_entities)
        self.assertIs(kwargs["request_factory"], server.Request)
        self.assertIs(kwargs["environ"], server.os.environ)

    def test_selection_preserves_live_discovery_and_phrase_dependencies(self):
        with patch.object(server.routine_request_selection, "select_routine_result") as select:
            server.select_routine_result("good morning", "kitchen")
        kwargs = select.call_args.kwargs
        self.assertIs(kwargs["connect"], server.ha_device_connection)
        self.assertIs(kwargs["movie_parser"], server.parse_movie_request)
        self.assertIs(kwargs["morning_phrases"], server.GOOD_MORNING_PHRASES)

    def test_turn_selection_uses_live_server_callback(self):
        with patch.object(server.routine_turn_orchestration, "select_routine_turn_result") as select:
            server.select_routine_turn_result("movie time", "lounge")
        kwargs = select.call_args.kwargs
        self.assertIs(kwargs["select"], server.select_routine_result)
        self.assertIs(kwargs["parse_movie"], server.parse_movie_request)

    def test_execution_forwards_approval_and_discovery(self):
        evidence: list[dict[str, Any]]
        evidence = []
        with patch.object(server.routine_turn_orchestration, "execute_routine_result") as execute:
            server.execute_routine_result("movie", evidence, approved=True)
        self.assertEqual(execute.call_args.args, ("movie", evidence))
        self.assertTrue(execute.call_args.kwargs["approved"])
        self.assertIs(execute.call_args.kwargs["connect"], server.ha_device_connection)
        self.assertIs(execute.call_args.kwargs["discovery"], server.script_discovery)


if __name__ == "__main__":
    unittest.main()
