"""Behavioural coverage for extracted media settings HTTP adapters."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

import media_settings_routes as routes


class MediaSettingsRoutesTests(TestCase):
    def setUp(self):
        self.handler = Mock()
        self.music = Mock()
        self.inventory = Mock()
        self.inventory.InventoryResult.coerce.side_effect = lambda value: value
        self.connection = Mock(return_value="ha")
        self.read_inventory = Mock(return_value=SimpleNamespace(
            inventory=[{"entity_id": "media_player.kitchen",
                        "declan_music_assistant": True,
                        "attributes": {"friendly_name": "Kitchen"},
                        "declan_area": "kitchen", "state": "idle"}],
            error=None,
        ))
        self.read_areas = Mock(return_value=[{"id": "kitchen"}])
        self.labels = Mock(return_value={"kitchen": "Kitchen"})
        self.approved = Mock()
        self.approved.load.return_value = {"kitchen": "media_player.kitchen"}

    def players(self, body=None):
        routes.approved_player_settings(
            self.handler, body, ha_device_connection=self.connection,
            ha_inventory=self.inventory, read_music_inventory_result=self.read_inventory,
            read_ha_areas=self.read_areas, approved_area_labels=self.labels,
            approved_media_players=self.approved,
        )

    def test_spotify_read(self):
        self.music.spotify_credentials.return_value = ({"client_id": "redacted"}, "environment")
        routes.spotify_settings(self.handler, music=self.music)
        self.handler.send_json.assert_called_once_with(200, {"source": "environment"})

    def test_spotify_write_and_validation(self):
        routes.spotify_settings(
            self.handler, {"client_id": "id", "client_secret": "secret"}, music=self.music,
        )
        self.music.save_spotify_credentials.assert_called_once_with("id", "secret")
        self.handler.send_json.assert_called_once_with(200, {"source": "saved"})
        self.handler.reset_mock()
        self.music.save_spotify_credentials.side_effect = ValueError("bad")
        routes.spotify_settings(self.handler, {}, music=self.music)
        self.handler.send_json.assert_called_once_with(
            400, {"error": "Enter both a valid Spotify Client ID and Client Secret."},
        )

    def test_spotify_storage_error(self):
        self.music.spotify_credentials.side_effect = OSError("locked")
        routes.spotify_settings(self.handler, music=self.music)
        self.handler.send_json.assert_called_once_with(
            503, {"error": "Spotify settings are unavailable."},
        )

    def test_players_read(self):
        self.players()
        self.handler.send_json.assert_called_once_with(
            200, {"configured": True, "rooms": ["kitchen"],
                  "room_labels": {"kitchen": "Kitchen"},
                  "selected": {"kitchen": "media_player.kitchen"},
                  "players": [{"entity_id": "media_player.kitchen", "name": "Kitchen",
                               "area": "kitchen", "state": "idle"}]},
        )

    def test_players_save(self):
        self.players({"rooms": {"kitchen": "media_player.kitchen"}})
        self.approved.save.assert_called_once_with({"kitchen": "media_player.kitchen"})

    def test_players_reject_unknown_player(self):
        self.players({"rooms": {"kitchen": "media_player.unregistered"}})
        self.handler.send_json.assert_called_once_with(
            400, {"error": "Select registered Music Assistant players for known Home Assistant areas."},
        )
        self.approved.save.assert_not_called()

    def test_players_missing_ha(self):
        self.connection.return_value = None
        self.players()
        self.handler.send_json.assert_called_once_with(
            503, {"error": "Home Assistant is not configured."},
        )

    def test_players_inventory_failure(self):
        self.read_inventory.return_value = SimpleNamespace(inventory=[], error="unavailable")
        self.players()
        self.handler.send_json.assert_called_once_with(
            503, {"error": "Home Assistant media inventory is unavailable."},
        )
