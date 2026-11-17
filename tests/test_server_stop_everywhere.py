"""Regression tests for the server's generic Stop routing."""
import unittest
from unittest.mock import patch

import server


class ServerStopEverywhereTests(unittest.TestCase):
    def test_grouped_players_are_stopped_once_via_group(self):
        group = "media_player.everywhere_ma"
        kitchen = "media_player.kitchen_ma"
        bedroom = "media_player.bedroom_ma"
        players = {
            group: {"state": "playing", "attributes": {"group_members": [kitchen, bedroom]}},
            kitchen: {"state": "playing", "attributes": {}},
            bedroom: {"state": "playing", "attributes": {}},
        }
        destinations = {"everywhere": group, "kitchen": kitchen, "bedroom": bedroom}
        calls = []

        def dispatch(connection, path, data, **kwargs):
            calls.append(data["entity_id"])
            players[data["entity_id"]]["state"] = "idle"

        with patch.object(server, 'read_music_inventory_result', return_value=([], None)), \
             patch.object(server.music, "music_players", return_value=(destinations, players)), \
             patch.object(server.music, "request", side_effect=dispatch), \
             patch.object(server.music, "wait_for",
                          side_effect=lambda conn, entity, predicate, **kw: predicate(players[entity])):
            _, outcome, reply = server.stop_everywhere_output(object())
        self.assertEqual(outcome, "confirmed", reply)
        self.assertEqual(calls, [group])

    def test_unapproved_players_are_not_stopped_by_server(self):
        approved = "media_player.kitchen_ma"
        players = {
            approved: {"state": "playing", "attributes": {}},
            "media_player.unapproved": {"state": "playing", "attributes": {}},
        }
        calls = []

        def dispatch(connection, path, data, **kwargs):
            calls.append(data["entity_id"])
            players[data["entity_id"]]["state"] = "idle"

        with patch.object(server, 'read_music_inventory_result', return_value=([], None)), \
             patch.object(server.music, "music_players",
                          return_value=({"kitchen": approved}, players)), \
             patch.object(server.music, "request", side_effect=dispatch), \
             patch.object(server.music, "wait_for",
                          side_effect=lambda conn, entity, predicate, **kw: predicate(players[entity])):
            _, outcome, reply = server.stop_everywhere_output(object())
        self.assertEqual(outcome, "confirmed", reply)
        self.assertEqual(calls, [approved])


if __name__ == "__main__":
    unittest.main()
