"""Regression tests for HA routine selection extraction."""
import unittest
from unittest.mock import patch

import server
import routine_request_selection as extracted
from routine_selection_results import RoutineSelectionKind


class RoutineSelectionExtractionTests(unittest.TestCase):
    def test_movie_parser_wrapper_uses_existing_room_and_app_config(self):
        with patch.object(extracted, "parse_movie_request", return_value="sentinel") as helper:
            self.assertEqual(server.parse_movie_request("movie time"), "sentinel")
        self.assertEqual(helper.call_args.kwargs["rooms"], server.MOVIE_ROOMS)
        self.assertIs(helper.call_args.kwargs["apps"], server.MOVIE_APPS)

    def test_selector_wrapper_preserves_patchable_dependencies(self):
        with patch.object(extracted, "select_routine_result", return_value="sentinel") as helper:
            self.assertEqual(server.select_routine_result("good night", None), "sentinel")
        kwargs = helper.call_args.kwargs
        self.assertIs(kwargs["connect"], server.ha_device_connection)
        self.assertIs(kwargs["discovery_module"], server.script_discovery)
        self.assertIs(kwargs["movie_parser"], server.parse_movie_request)
        self.assertIs(kwargs["sexy_commands"], server.SEXY_TIME_COMMANDS)

    def test_movie_request_direction_and_room(self):
        self.assertEqual(server.parse_movie_request("start movie time in bedroom"), ("start", "bedroom", None))
        self.assertEqual(server.parse_movie_request("end movie time"), ("end", None, None))

    def test_house_status_missing_ha_is_explicit(self):
        with patch.object(server, "ha_device_connection", return_value=None):
            result = server.select_routine_result("house status", None)
        assert result is not None
        self.assertEqual(result.kind, RoutineSelectionKind.HOUSE_STATUS_MISSING)

    def test_unconfigured_ha_does_not_select_other_routines(self):
        with patch.object(server, "ha_device_connection", return_value=None):
            self.assertIsNone(server.select_routine_result("good morning", None))


if __name__ == "__main__":
    unittest.main()
