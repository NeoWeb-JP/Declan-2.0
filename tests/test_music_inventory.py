"""Check registry discovery when HA attributes contain native datetime values."""

import io
import json
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.parse import urlsplit

import music
import server


class MusicInventoryTests(TestCase):
    def test_native_datetime_does_not_break_discovery_or_group_membership(self):
        entity = "media_player.utility_queue"
        satellite = "assist_satellite.utility"
        timestamp = datetime(2026, 11, 11, 8, 30, tzinfo=timezone.utc)
        states = [
            {"entity_id": entity, "state": "playing", "attributes": {
                "friendly_name": "Utility Room", "media_title": "Country song",
                "media_content_id": "spotify:track:0JkIre0YxNmKGMU5V7ZiDx",
                "media_position_updated_at": timestamp,
                "group_members": [entity],
            }},
            {"entity_id": satellite, "state": "idle", "attributes": {"last_seen": timestamp}},
        ]
        metadata = [dict(entity_id=row["entity_id"], declan_area="Utility Room",
                         declan_device="utility-device", declan_music_assistant=index == 0)
                    for index, row in enumerate(states)]
        calls = []

        def open_request(request, timeout):
            path = urlsplit(request.full_url).path
            calls.append(path)
            if path == "/api/states":
                # HA's REST encoder converts native datetime attributes to ISO strings.
                return io.BytesIO(json.dumps(states, default=lambda value: value.isoformat()).encode())
            self.assertEqual(path, "/api/template")
            template = json.loads(request.data)["template"]
            self.assertNotIn("entity.attributes", template)
            self.assertIn("integration_entities('music_assistant')", template)
            # Only registry metadata crosses Jinja's strict JSON encoder.
            return io.BytesIO(json.dumps(metadata).encode())

        opener = Mock()
        opener.open.side_effect = open_request
        inventory, error = server.read_music_inventory(("http://ha.invalid", {}, opener))
        self.assertIsNone(error)
        self.assertEqual(calls, ["/api/states", "/api/template"])
        player = inventory[0]
        self.assertEqual(player["attributes"]["media_position_updated_at"], timestamp.isoformat())
        self.assertEqual(player["attributes"]["group_members"], [entity])
        destinations, players = music.music_players(inventory)
        self.assertEqual(destinations["utility room"], entity)
        self.assertEqual(players[entity]["attributes"]["media_title"], "Country song")
        self.assertEqual(inventory[1]["declan_device"], "utility-device")

    def test_unavailable_states_do_not_produce_partial_inventory(self):
        opener = Mock()
        opener.open.side_effect = HTTPError("http://ha.invalid/api/states", 401, "Unauthorized", {}, None)
        self.assertEqual(server.read_music_inventory(("http://ha.invalid", {}, opener)), (None, "unavailable"))
        self.assertEqual(opener.open.call_count, 1)

    def test_unavailable_registry_does_not_produce_partial_inventory(self):
        opener = Mock()
        opener.open.side_effect = [io.BytesIO(b"[]"),
                                  HTTPError("http://ha.invalid/api/template", 500, "Error", {}, None)]
        self.assertEqual(server.read_music_inventory(("http://ha.invalid", {}, opener)), (None, "unavailable"))
