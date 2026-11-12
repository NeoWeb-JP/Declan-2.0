"""Regression coverage for approved per-area media player routing."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import approved_media_players as approved
import music


class ApprovedMediaPlayerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"DECLAN_APPROVED_MEDIA_PLAYERS_FILE":
                                     str(Path(self.temp.name) / "players.json")})
        env.start()
        self.addCleanup(env.stop)

    def test_only_approved_players_are_selected(self):
        approved.save({"Kitchen": "media_player.kitchen_declan_voice_assistant",
                       "everywhere": "media_player.everywhere_2"})
        inventory = [
            {"entity_id": "media_player.kitchen_declan_voice_assistant",
             "state": "playing", "declan_music_assistant": True},
            {"entity_id": "media_player.kitchen_sonos",
             "state": "playing", "declan_music_assistant": True},
            {"entity_id": "media_player.everywhere_2",
             "state": "idle", "declan_music_assistant": True},
        ]
        destinations, players = music.music_players(inventory)
        self.assertEqual(destinations, {
            "kitchen": "media_player.kitchen_declan_voice_assistant",
            "everywhere": "media_player.everywhere_2"})
        self.assertNotIn("media_player.kitchen_sonos", players)

    def test_missing_or_non_music_assistant_player_fails_closed(self):
        approved.save({"kitchen": "media_player.kitchen_sonos",
                       "study": "media_player.missing"})
        destinations, players = music.music_players([
            {"entity_id": "media_player.kitchen_sonos", "state": "playing",
             "declan_music_assistant": False}])
        self.assertEqual(destinations, {"kitchen": None, "study": None})
        self.assertEqual(players, {})

    def test_invalid_mapping_is_rejected(self):
        with self.assertRaises(ValueError):
            approved.save({"kitchen": "switch.kitchen"})
        with self.assertRaises(ValueError):
            approved.save({"kitchen": "media_player.kitchen;bad"})

    def test_playback_control_does_not_use_unapproved_player(self):
        approved.save({"kitchen": "media_player.kitchen_declan_voice_assistant"})
        inventory = [
            {"entity_id": "media_player.kitchen_declan_voice_assistant", "state": "idle",
             "declan_music_assistant": True, "attributes": {}},
            {"entity_id": "media_player.kitchen_sonos", "state": "playing",
             "declan_music_assistant": True, "attributes": {}},
        ]
        with patch.object(music, "request") as request:
            _, outcome = music.control(("media_next_track", "kitchen"), object(),
                                       lambda connection: (inventory, None))
        self.assertEqual(outcome, "unavailable")
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
