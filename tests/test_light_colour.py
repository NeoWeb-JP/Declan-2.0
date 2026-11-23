"""Colour requests: parsing, routing, dispatch payloads and verification."""
import json
import os
from typing import Any
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import urlsplit

from result_pairs import pair_of
from test_home_assistant import HA_ENV, FakeHomeAssistant, light

import server
from declan.ha import lighting_intents
from declan.ha.light_command_parsing import parse_light_command


class ColourParsingTests(TestCase):
    def test_colour_phrases(self):
        cases = {
            "turn on the utility room spotlights and set them to red": ("utility room spotlights", "red"),
            "turn the lamp on and make it light blue": ("lamp", "light blue"),
            "set the kitchen lights to warm white": ("kitchen lights", "warm white"),
            "make the utility room spotlights yellow": ("utility room spotlights", "yellow"),
            "change the spots to the colour green": ("spots", "green"),
            "utility room spotlights yellow": ("utility room spotlights", "yellow"),
            "set the bedroom to blue": ("bedroom", "blue"),
            "make them pink": ("them", "pink"),
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(lighting_intents.parse_colour_command(phrase), expected)
                self.assertTrue(lighting_intents.matches(phrase, parse_light_command))

    def test_not_colour(self):
        for phrase in ("turn the lights on", "turn off the lights", "set the volume to 30 percent",
                       "play red by taylor swift", "set the tv to blue", "turn on the kitchen light",
                       "set the kitchen lights to 40 percent", "make the lights brighter"):
            with self.subTest(phrase=phrase):
                self.assertIsNone(lighting_intents.parse_colour_command(phrase))


class ColourHomeAssistant(FakeHomeAssistant):
    """The shared fake, plus colour state and a colour-capable spotlight."""

    def __init__(self):
        super().__init__()
        spot = light("utility_room_spotlights", "off", brightness=255,
                     supported_color_modes=["color_temp", "hs"], hs_color=[0, 0], color_temp_kelvin=4000)
        spot["attributes"]["friendly_name"] = "Utility Room Spotlights"
        self.entities[spot["entity_id"]] = spot
        # First area: what the fake reports as the speaking satellite's room.
        self.areas.insert(0, ["Utility Room", ["light.utility_room_spotlights"]])
        self.colour_applies = True
        self.slow_services = False

    def open(self, request, timeout):
        path = urlsplit(request.full_url).path
        response = super().open(request, timeout)
        data = json.loads(request.data) if request.data else None
        if self.apply and self.colour_applies and path == "/api/services/light/turn_on" and isinstance(data, dict):
            entities = data["entity_id"]
            for entity in entities if isinstance(entities, list) else [entities]:
                attributes = self.entities[entity]["attributes"]
                if "hs_color" in data:
                    attributes["hs_color"] = data["hs_color"]
                if "color_temp_kelvin" in data:
                    attributes["color_temp_kelvin"] = data["color_temp_kelvin"]
        if self.slow_services and path.startswith("/api/services/light/"):
            raise TimeoutError("service call still running")
        return response


class ColourExecutionTests(TestCase):
    def setUp(self):
        self.ha = ColourHomeAssistant()
        self.enterContext(patch.dict(os.environ, HA_ENV))
        self.enterContext(patch.object(server, "build_opener", return_value=self.ha))

    def run_light(self, phrase, expected, **kwargs):
        steps: list[dict[str, Any]] = []
        reply, outcome = pair_of(server.handle_light_request_result)(
            server.history.normalize_phrase(phrase), action_results=steps, **kwargs)
        self.assertEqual(outcome, expected, reply)
        return reply, steps

    def writes(self):
        return [(route, data) for route, data in self.ha.calls if "/services/" in route]

    def test_turn_on_and_set_colour_in_one_command(self):
        _, steps = self.run_light("Turn on the utility room spotlights and set them to red.", "confirmed")
        spot = self.ha.entities["light.utility_room_spotlights"]
        self.assertEqual(spot["state"], "on")
        self.assertEqual(spot["attributes"]["hs_color"], [0, 100])
        self.assertEqual(self.writes(), [("/api/services/light/turn_on", {
            "entity_id": "light.utility_room_spotlights", "hs_color": [0, 100]})])
        self.assertIn("set colour to red", {step["action"] for step in steps})

    def test_white_shades_use_colour_temperature(self):
        self.run_light("set the utility room spotlights to warm white", "confirmed")
        self.assertEqual(self.writes(), [("/api/services/light/turn_on", {
            "entity_id": "light.utility_room_spotlights", "color_temp_kelvin": 2700})])

    def test_room_name_targets_lights_in_that_room(self):
        self.run_light("make the utility room blue", "confirmed")
        self.assertEqual(self.ha.entities["light.utility_room_spotlights"]["attributes"]["hs_color"], [240, 100])

    def test_lights_without_colour_are_left_alone(self):
        reply, steps = self.run_light("make the study light red", "unavailable")
        self.assertIn("colour control", reply)
        self.assertEqual(self.writes(), [])
        self.assertEqual({step["detail"] for step in steps}, {"colour unsupported"})

    def test_unreported_colour_is_not_claimed(self):
        self.ha.colour_applies = False
        with patch.object(server, "sleep"):
            reply, _ = self.run_light("make the utility room spotlights green", "unverified")
        self.assertIn("couldn't confirm", reply)

    def test_it_uses_the_last_lights(self):
        self.run_light("make it purple", "confirmed", last_lights=("utility room spotlights",))
        self.assertEqual(self.ha.entities["light.utility_room_spotlights"]["attributes"]["hs_color"], [275, 100])
        reply, _ = self.run_light("make it purple", "unresolved")
        self.assertIn("Which lights", reply)

    def test_them_without_history_means_the_speakers_room(self):
        self.run_light("Turn them on and set them to pink.", "confirmed", origin_device="satellite")
        spot = self.ha.entities["light.utility_room_spotlights"]
        self.assertEqual((spot["state"], spot["attributes"]["hs_color"]), ("on", [330, 60]))
        self.assertEqual(self.ha.entities["light.study_light"]["state"], "off")

    def test_slow_service_call_is_still_verified(self):
        self.ha.slow_services = True
        self.ha.entities["light.utility_room_spotlights"]["state"] = "on"
        reply, steps = self.run_light("utility room spotlights off", "confirmed")
        self.assertEqual(self.ha.entities["light.utility_room_spotlights"]["state"], "off")
        self.assertEqual({step["status"] for step in steps}, {"confirmed"})
        self.ha.apply = False
        self.ha.entities["light.utility_room_spotlights"]["state"] = "on"
        with patch.object(server, "sleep"):
            reply, _ = self.run_light("utility room spotlights off", "unverified")
        self.assertIn("couldn't confirm", reply)
