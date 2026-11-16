"""Regression coverage for native routine dispatch and guest command routing."""
import unittest
from unittest.mock import patch
import server


class RoutineDispatchTests(unittest.TestCase):
    def test_movie_direction_is_parsed_without_mapping(self):
        self.assertEqual(server.parse_movie_request("end movie time")[0], "end")
        self.assertEqual(server.parse_movie_request("stop cinema mode")[0], "end")

    def test_house_status_resolves_from_ha_inventory_only(self):
        script = {"entity_id": "script.house_status", "name": "House Status", "safe": True}
        with patch.object(server, "ha_device_connection", return_value=("url", {}, object())), \
             patch.object(server.script_discovery, "discover", return_value=([script], None)):
            for phrase in ("what is the status of the house", "house status", "how is the house"):
                with self.subTest(phrase=phrase):
                    self.assertEqual(server.select_routine(phrase, None), ("auto:script.house_status", {}))

    def test_missing_house_status_never_falls_through_to_device_lookup(self):
        with patch.object(server, "ha_device_connection", return_value=None):
            self.assertEqual(server.select_routine_turn("how is the house", None),
                             (("unconfigured_house_status", {}), None))

    def test_no_saved_mapping_can_override_ha_script(self):
        script = {"entity_id": "script.good_night", "name": "Good Night", "safe": True}
        with patch.object(server, "ha_device_connection", return_value=("url", {}, object())), \
             patch.object(server.script_discovery, "discover", return_value=([script], None)), \
             patch.object(server.routine_registry, "load", side_effect=AssertionError("legacy mapping accessed")):
            self.assertEqual(server.select_routine("good night", None), ("auto:script.good_night", {}))

    def test_other_device_status_is_not_intercepted(self):
        with patch.object(server, "ha_device_connection", return_value=None):
            self.assertIsNone(server.select_routine("what is the status of the projector", None))

    def test_end_movie_time_never_selects_start_only_script(self):
        script = {"entity_id": "script.movie_time", "name": "Movie Time", "safe": True}
        with patch.object(server, "ha_device_connection", return_value=("url", {}, object())), \
             patch.object(server.script_discovery, "discover", return_value=([script], None)):
            self.assertIsNone(server.select_routine("end movie time", None))
            self.assertEqual(server.select_routine("movie time", None),
                             ("auto:script.movie_time", {"operation": "toggle", "room": "lounge"}))

    def test_guest_read_phrases_exist(self):
        self.assertEqual(server.GUEST_COMMANDS["who's in charge"], "check")

    def test_guest_departure_variants_clear_guest_mode(self):
        for phrase in (
            "all guests have left", "all guest have left",
            "the guest has left", "our guest has left",
            "guests have left", "guest has left", "everyone has left",
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(server.GUEST_COMMANDS[phrase], "clear")


if __name__ == "__main__":
    unittest.main()
