"""Regression coverage for native routine dispatch and guest command routing."""
import unittest
from unittest.mock import patch
import server


class RoutineDispatchTests(unittest.TestCase):
    def test_end_movie_time_not_overridden_by_saved_start_mapping(self):
        mapped = ("movie", {"script": "script.movie", "phrases": ["end movie time"]}, {})
        with patch.object(server.routine_registry, "match", return_value=mapped):
            result = server.select_routine("end movie time", None)
        self.assertEqual(result[0], "movie")
        self.assertEqual(result[1]["movie_action"], "end")

    def test_stop_cinema_mode_uses_end_direction(self):
        self.assertEqual(server.parse_movie_request("stop cinema mode")[0], "end")

    def test_house_status_resolves_configured_routine(self):
        mapping = {"house_status": {"script": "script.house_status", "phrases": ["house status"], "fields": {}, "sensitive": False}}
        with patch.object(server.routine_registry, "load", return_value=mapping):
            for phrase in ("what is the status of the house", "house status", "how is the house"):
                with self.subTest(phrase=phrase):
                    self.assertEqual(server.select_routine(phrase, None), ("custom:house_status", {}))

    def test_house_status_without_mapping_is_not_a_device_lookup(self):
        with patch.object(server.routine_registry, "load", return_value={}):
            selection = server.select_routine("what is the status of the house", None)
        self.assertEqual(selection, ("unconfigured_house_status", {}))
        self.assertEqual(server.execute_routine(selection, [])[1], "not_configured")

    def test_other_device_status_is_not_intercepted(self):
        with patch.object(server.routine_registry, "load", return_value={}):
            self.assertIsNone(server.house_status_routine("what is the status of the projector"))

    def test_guest_read_phrases_exist(self):
        self.assertEqual(server.GUEST_COMMANDS["who's in charge"], "check")


if __name__ == "__main__":
    unittest.main()
