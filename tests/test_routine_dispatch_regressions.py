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
