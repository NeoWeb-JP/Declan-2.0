"""Regression tests for household-wide Music Assistant Stop."""
import unittest
from unittest.mock import patch

from declan.music import music


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

    def test_everywhere_group_members_are_not_stopped_twice(self):
        group = "media_player.everywhere_ma"
        kitchen = "media_player.kitchen_ma"
        bedroom = "media_player.bedroom_ma"
        destinations = {"everywhere": group, "kitchen": kitchen, "bedroom": bedroom}
        players = {
            group: {"state": "playing", "attributes": {"group_members": [kitchen, bedroom]}},
            kitchen: {"state": "playing", "attributes": {}},
            bedroom: {"state": "playing", "attributes": {}},
        }
        calls = []

        def stop(connection, path, data, **kwargs):
            calls.append(data["entity_id"])
            players[data["entity_id"]]["state"] = "idle"

        with patch.object(music, "music_players", return_value=(destinations, players)), \
             patch.object(music, "request", side_effect=stop), \
             patch.object(music, "wait_for", side_effect=lambda conn, entity, predicate, **kw: predicate(players[entity])):
            reply, outcome = music.control(
                ("media_stop", None), ("http://ha", {}, None), lambda conn: ([], None)
            )
        self.assertEqual(outcome, "confirmed", reply)
        self.assertEqual(calls, [group])

    def test_unapproved_playing_player_is_not_stopped(self):
        approved = "media_player.kitchen_ma"
        unapproved = "media_player.unapproved"
        players = {
            approved: {"state": "playing", "attributes": {}},
            unapproved: {"state": "playing", "attributes": {}},
        }
        calls = []

        def stop(connection, path, data, **kwargs):
            calls.append(data["entity_id"])
            players[data["entity_id"]]["state"] = "idle"

        with patch.object(music, "music_players",
                          return_value=({"kitchen": approved}, players)), \
             patch.object(music, "request", side_effect=stop), \
             patch.object(music, "wait_for",
                          side_effect=lambda conn, entity, predicate, **kw: predicate(players[entity])):
            reply, outcome = music.control(
                ("media_stop", None), ("http://ha", {}, None), lambda conn: ([], None)
            )
        self.assertEqual(outcome, "confirmed", reply)
        self.assertEqual(calls, [approved])
        self.assertEqual(players[unapproved]["state"], "playing")

    def test_failed_stop_does_not_claim_success(self):
        entity = "media_player.kitchen_ma"
        players = {entity: {"state": "playing", "attributes": {}}}
        with patch.object(music, "music_players",
                          return_value=({"kitchen": entity}, players)), \
             patch.object(music, "request"), \
             patch.object(music, "wait_for", return_value=False):
            reply, outcome = music.control(
                ("media_stop", None), ("http://ha", {}, None), lambda conn: ([], None)
            )
        self.assertEqual(outcome, "partial", reply)
        self.assertIn("couldn't verify", reply)

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
