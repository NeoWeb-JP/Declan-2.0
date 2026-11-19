"""Verify the Music Assistant compatibility environment gate fails closed."""
import os
import unittest
from unittest.mock import patch

from declan.music import music


class MusicAssistantCompatibilityEnvironmentTests(unittest.TestCase):
    REGISTERED = [
        {"entity_id": "media_player.kitchen_ma", "state": "idle",
         "declan_music_assistant": True, "declan_area": "Kitchen",
         "declan_device": "device-kitchen"},
        {"entity_id": "media_player.everywhere", "state": "idle",
         "declan_music_assistant": True,
         "attributes": {"friendly_name": "Everywhere"}},
    ]

    def resolve(self, settings, inventory=None):
        with patch.dict(os.environ, settings, clear=True), patch.object(
                music.approved_media_players, "resolve", return_value=None):
            return music.music_players(self.REGISTERED if inventory is None else inventory)

    def test_unset_empty_and_non_exact_opt_in_fail_closed(self):
        for settings in ({}, {"DECLAN_ALLOW_UNCONFIGURED_MA": ""},
                         {"DECLAN_ALLOW_UNCONFIGURED_MA": "0"},
                         {"DECLAN_ALLOW_UNCONFIGURED_MA": "true"},
                         {"DECLAN_ALLOW_UNCONFIGURED_MA": " 1 "}):
            with self.subTest(settings=settings):
                self.assertEqual(self.resolve(settings), ({}, {}))

    def test_exact_opt_in_only_discovers_registered_players(self):
        inventory = self.REGISTERED + [
            {"entity_id": "media_player.unregistered", "state": "idle",
             "declan_area": "Kitchen", "declan_device": "device-other"}]
        destinations, players = self.resolve(
            {"DECLAN_ALLOW_UNCONFIGURED_MA": "1"}, inventory)
        self.assertEqual(destinations["kitchen"], "media_player.kitchen_ma")
        self.assertEqual(destinations["everywhere"], "media_player.everywhere")
        self.assertNotIn("media_player.unregistered", players)

    def test_opt_in_does_not_enable_unregistered_inventory(self):
        inventory = [{"entity_id": "media_player.unregistered", "state": "idle",
                      "declan_area": "Kitchen"}]
        self.assertEqual(self.resolve(
            {"DECLAN_ALLOW_UNCONFIGURED_MA": "1"}, inventory), ({}, {}))

    def test_approved_mapping_takes_precedence_without_opt_in(self):
        approved = {"kitchen": "media_player.kitchen_ma"}
        with patch.dict(os.environ, {}, clear=True), patch.object(
                music.approved_media_players, "resolve", return_value=approved):
            destinations, players = music.music_players(self.REGISTERED)
        self.assertEqual(destinations, approved)
        self.assertEqual(set(players), {"media_player.kitchen_ma"})


if __name__ == "__main__":
    unittest.main()
