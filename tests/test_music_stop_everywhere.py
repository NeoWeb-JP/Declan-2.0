"""Regression tests for household-wide Music Assistant Stop."""
import unittest
from unittest.mock import patch

import music


class StopEverywhereTests(unittest.TestCase):
    def test_unqualified_stop_stops_each_active_approved_destination(self):
        destinations = {
            "kitchen": "media_player.kitchen_ma",
            "bedroom": "media_player.bedroom_ma",
            "everywhere": "media_player.everywhere_ma",
        }
        players = {
            "media_player.kitchen_ma": {"state": "playing"},
            "media_player.bedroom_ma": {"state": "paused"},
            "media_player.everywhere_ma": {"state": "idle"},
        }
        calls = []

        def stop(connection, path, data, **kwargs):
            self.assertEqual(path, "/api/services/media_player/media_stop")
            calls.append(data["entity_id"])
            players[data["entity_id"]]["state"] = "idle"

        with patch.object(music, "music_players", return_value=(destinations, players)), \
             patch.object(music, "request", side_effect=stop), \
             patch.object(music, "wait_for", side_effect=lambda conn, entity, predicate, **kw: predicate(players[entity])):
            reply, outcome = music.control(
                ("media_stop", None), ("http://ha", {}, None),
                lambda conn: ([], None), origin="assist_satellite.kitchen",
                assist=True, read_areas=lambda conn, origin: {"kitchen": []}
            )
        self.assertEqual(outcome, "confirmed", reply)
        self.assertEqual(set(calls), {"media_player.kitchen_ma", "media_player.bedroom_ma"})

    def test_explicit_room_stop_does_not_become_household_wide(self):
        destinations = {"kitchen": "media_player.kitchen_ma", "everywhere": "media_player.everywhere_ma"}
        players = {
            "media_player.kitchen_ma": {"state": "playing", "attributes": {}},
            "media_player.everywhere_ma": {"state": "idle", "attributes": {}},
        }
        calls = []

        def stop(connection, path, data, **kwargs):
            calls.append(data["entity_id"])
            players[data["entity_id"]]["state"] = "idle"

        with patch.object(music, "music_players", return_value=(destinations, players)), \
             patch.object(music, "request", side_effect=stop), \
             patch.object(music, "wait_for", side_effect=lambda conn, entity, predicate, **kw: predicate(players[entity])):
            reply, outcome = music.control(
                ("media_stop", "kitchen"), ("http://ha", {}, None), lambda conn: ([], None)
            )
        self.assertEqual(outcome, "confirmed", reply)
        self.assertEqual(calls, ["media_player.kitchen_ma"])


if __name__ == "__main__":
    unittest.main()
