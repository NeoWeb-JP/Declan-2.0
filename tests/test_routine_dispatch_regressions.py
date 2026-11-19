"""Regression coverage for native routine dispatch and guest command routing."""
from typing import Any
import unittest
from unittest.mock import patch
import legacy_wire
import server


class RoutineDispatchTests(unittest.TestCase):
    def test_sexy_aliases_preserve_direction_and_use_background_receipt(self):
        script: dict[str, Any]
        script = {"entity_id": "script.bedroom_romance", "name": "Declan - Sexy Time Controller",
                  "safe": True, "fields": ["operation", "requested_action"]}
        with patch.object(server, "ha_device_connection", return_value=("http://ha", {}, object())), \
             patch.object(server.script_discovery, "discover_result", return_value=server.script_discovery.DiscoveryResult(tuple([script]), None)), \
             patch.object(server.script_discovery, "_enqueue_provider", return_value=("requested", "started", "job")) as enqueue, \
             patch.object(server.script_discovery, "_execute_provider", side_effect=AssertionError("waited for music")):
            for phrase, action in server.SEXY_TIME_COMMANDS.items():
                selection = legacy_wire.select_routine(phrase, None)
                self.assertEqual(selection[0], "auto:" + script["entity_id"])
                self.assertEqual(selection[1]["operation"], action)
                self.assertEqual(selection[1]["requested_action"], action)
                self.assertEqual(selection[1]["_declan_reply_category"], "sexy")
                self.assertEqual(legacy_wire.execute_routine(selection, [])[1], "started")
                self.assertEqual(enqueue.call_args.args[2], {"operation": action, "requested_action": action})

    def test_end_sexy_time_does_not_run_a_start_only_script(self):
        script: dict[str, Any]
        script = {"entity_id": "script.sexy_time", "name": "Sexy Time", "safe": True, "fields": []}
        with patch.object(server, "ha_device_connection", return_value=("http://ha", {}, object())), \
             patch.object(server.script_discovery, "discover_result", return_value=server.script_discovery.DiscoveryResult(tuple([script]), None)):
            self.assertIsNone(legacy_wire.select_routine("end sexy time", None))
            self.assertIsNotNone(legacy_wire.select_routine("sexy time", None))

    def test_night_aliases_use_live_script_background_execution(self):
        script: dict[str, Any]
        script = {"entity_id": "script.declan_good_night_shared_local_routine",
                  "name": "Declan - Good Night - Shared Local Routine", "safe": True}
        with patch.object(server, "ha_device_connection", return_value=("http://ha", {}, object())), \
             patch.object(server.script_discovery, "discover_result", return_value=server.script_discovery.DiscoveryResult(tuple([script]), None)), \
             patch.object(server.script_discovery, "_enqueue_provider", return_value=("requested", "started", "job")) as enqueue, \
             patch.object(server.script_discovery, "_execute_provider", side_effect=AssertionError("waited for bedtime")):
            for phrase in (*server.GOOD_NIGHT_PHRASES, "declan good night shared local routine"):
                selection = legacy_wire.select_routine(phrase, None)
                self.assertEqual(selection, ("auto:" + script["entity_id"],
                    {"_declan_background": True, "_declan_reply_category": "night"}))
                self.assertEqual(legacy_wire.execute_routine(selection, [])[1], "started")
                self.assertEqual(enqueue.call_args.args[2], {})

    def test_morning_aliases_and_native_name_use_background_execution(self):
        script: dict[str, Any]
        script = {"entity_id": "script.declan_good_morning_shared_local_routine",
                  "name": "Declan - Good Morning - Shared Local Routine", "safe": True}
        with patch.object(server, "ha_device_connection", return_value=("http://ha", {}, object())), \
             patch.object(server.script_discovery, "discover_result", return_value=server.script_discovery.DiscoveryResult(tuple([script]), None)), \
             patch.object(server.script_discovery, "_enqueue_provider", return_value=("requested", "started", "job")) as enqueue, \
             patch.object(server.script_discovery, "_execute_provider", side_effect=AssertionError("waited for morning")):
            for phrase in (*server.GOOD_MORNING_PHRASES, "declan good morning shared local routine"):
                selection = legacy_wire.select_routine(phrase, None)
                self.assertEqual(selection, ("auto:" + script["entity_id"],
                    {"_declan_background": True, "_declan_reply_category": "morning"}))
                self.assertEqual(legacy_wire.execute_routine(selection, [])[1], "started")
                self.assertEqual(enqueue.call_args.args[2], {})

    def test_movie_direction_is_parsed_without_mapping(self):
        self.assertEqual(server.parse_movie_request("end movie time")[0], "end")
        self.assertEqual(server.parse_movie_request("stop cinema mode")[0], "end")

    def test_movie_requested_action_field_is_supported_for_all_directions(self):
        script: dict[str, Any]
        script = {"entity_id": "script.movie_time", "name": "Declan - Movie Time - Shared Local Routine",
                  "safe": True, "fields": ["requested_action", "request_id", "routine_id"]}
        with patch.object(server, "ha_device_connection", return_value=("http://ha", {}, object())), \
             patch.object(server.script_discovery, "discover_result", return_value=server.script_discovery.DiscoveryResult(tuple([script]), None)):
            for phrase, action in (("start movie time", "start"), ("end movie time", "end"), ("movie time", "toggle")):
                selection = legacy_wire.select_routine(phrase, None)
                self.assertIsNotNone(selection)
                self.assertEqual(selection[0], "auto:script.movie_time")
                self.assertEqual(selection[1]["requested_action"], action)

    def test_house_status_resolves_from_ha_inventory_only(self):
        script: dict[str, Any]
        script = {"entity_id": "script.house_status", "name": "House Status", "safe": True}
        with patch.object(server, "ha_device_connection", return_value=("url", {}, object())), \
             patch.object(server.script_discovery, "discover_result", return_value=server.script_discovery.DiscoveryResult(tuple([script]), None)):
            for phrase in ("what is the status of the house", "house status", "how is the house"):
                with self.subTest(phrase=phrase):
                    self.assertEqual(legacy_wire.select_routine(phrase, None), ("auto:script.house_status", {"_declan_expect_response": True}))

    def test_missing_house_status_never_falls_through_to_device_lookup(self):
        with patch.object(server, "ha_device_connection", return_value=None):
            self.assertEqual(legacy_wire.select_routine_turn("how is the house", None),
                             (("unconfigured_house_status", {}), None))

    def test_no_saved_mapping_can_override_ha_script(self):
        script: dict[str, Any]
        script = {"entity_id": "script.good_night", "name": "Good Night", "safe": True}
        with patch.object(server, "ha_device_connection", return_value=("url", {}, object())), \
             patch.object(server.script_discovery, "discover_result", return_value=server.script_discovery.DiscoveryResult(tuple([script]), None)), \
             patch.object(server.routine_registry, "load", side_effect=AssertionError("legacy mapping accessed")):
            self.assertEqual(legacy_wire.select_routine("good night", None), ("auto:script.good_night",
                {"_declan_background": True, "_declan_reply_category": "night"}))

    def test_other_device_status_is_not_intercepted(self):
        with patch.object(server, "ha_device_connection", return_value=None):
            self.assertIsNone(legacy_wire.select_routine("what is the status of the projector", None))

    def test_end_movie_time_never_selects_start_only_script(self):
        script: dict[str, Any]
        script = {"entity_id": "script.movie_time", "name": "Movie Time", "safe": True}
        with patch.object(server, "ha_device_connection", return_value=("url", {}, object())), \
             patch.object(server.script_discovery, "discover_result", return_value=server.script_discovery.DiscoveryResult(tuple([script]), None)):
            self.assertIsNone(legacy_wire.select_routine("end movie time", None))
            self.assertEqual(legacy_wire.select_routine("movie time", None),
                             ("auto:script.movie_time", {"operation": "toggle", "movie_action": "toggle",
                                                           "action": "toggle", "room": "lounge",
                                                           "movie_room": "lounge", "_declan_background": True}))

    def test_house_status_requests_script_response(self):
        script: dict[str, Any]
        script = {"entity_id": "script.declan_home_health_summary",
                  "name": "Declan - Home Health Summary", "safe": True}
        with patch.object(server, "ha_device_connection", return_value=("url", {}, object())), \
             patch.object(server.script_discovery, "discover_result", return_value=server.script_discovery.DiscoveryResult(tuple([script]), None)), \
             patch.object(server.script_discovery, "_execute_provider",
                          return_value=("All doors closed.", "reported_success", None)) as execute:
            selection = legacy_wire.select_routine("what is the status of the house", None)
            self.assertEqual(selection[0], "auto:script.declan_home_health_summary")
            result = legacy_wire.execute_routine(selection, [])
            self.assertEqual(result[0], "All doors closed.")
            self.assertTrue(execute.call_args.kwargs["expect_response"])

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
