"""Owner rule (26 Nov 2026): light on/off replies don't repeat what was switched.

Success is just a comment on having to do it. A failure names the light only,
never its controller board ("ESP32 BRMesh Mood Lights" is read as "Mood Lights").
"""
import os
from typing import Any
from unittest import TestCase
from unittest.mock import patch

import server
import test_home_assistant as fixtures
from declan.ha.lighting_execution_dispatch import is_on_off, spoken_label
from result_pairs import pair_of


class SpokenLabelTests(TestCase):
    def test_drops_the_controller_name(self):
        self.assertEqual(spoken_label("ESP32 BRMesh Mood Lights", "ESP32 BRMesh", "mood"), "Mood Lights")
        self.assertEqual(spoken_label("esp32-c3-a1b2c3 Bed Light", "esp32-c3-a1b2c3", "bed"), "Bed Light")

    def test_keeps_names_that_are_just_the_device(self):
        self.assertEqual(spoken_label("Kitchen Lamp", "Kitchen Lamp", "kitchen_lamp"), "Kitchen Lamp")
        self.assertEqual(spoken_label("Kitchen Lamp", None, "kitchen_lamp"), "Kitchen Lamp")
        self.assertEqual(spoken_label("Lamp", "Lampshade", "lamp"), "Lamp")

    def test_falls_back_to_the_entity_id(self):
        self.assertEqual(spoken_label(None, "ESP32", "mood lights"), "mood lights")

    def test_on_off_only(self):
        self.assertTrue(is_on_off("on", None, None))
        self.assertFalse(is_on_off("on", 30, None))
        self.assertFalse(is_on_off("on", None, "red"))
        self.assertFalse(is_on_off("darker", None, None))


class OnOffReplyTests(TestCase):
    def setUp(self):
        self.ha = fixtures.FakeHomeAssistant()
        self.ha.entities["light.mood_lights"] = {
            "entity_id": "light.mood_lights", "state": "off", "declan_device_name": "ESP32 BRMesh",
            "attributes": {"friendly_name": "ESP32 BRMesh Mood Lights"}}
        self.enterContext(patch.dict(os.environ, fixtures.HA_ENV))
        self.enterContext(patch.object(server, "build_opener", return_value=self.ha))

    def run_light(self, phrase, expected):
        steps: list[dict[str, Any]] = []
        reply, outcome = pair_of(server.handle_light_request_result)(phrase, action_results=steps)
        self.assertEqual(outcome, expected, reply)
        return reply

    def test_success_is_a_comment_not_a_repeat(self):
        reply = self.run_light("turn on the mood lights", "confirmed")
        self.assertEqual(self.ha.entities["light.mood_lights"]["state"], "on")
        self.assertNotIn("Mood Lights", reply)
        self.assertNotIn("ESP32", reply)
        self.assertNotIn("is on", reply)
        reply = self.run_light("turn off the mood lights", "confirmed")
        self.assertNotIn("Mood Lights", reply)

    def test_full_name_still_works(self):
        self.run_light("turn on esp32 brmesh mood lights", "confirmed")
        self.assertEqual(self.ha.entities["light.mood_lights"]["state"], "on")

    def test_failure_names_only_the_light(self):
        self.ha.apply = False
        with patch.object(server, "sleep"):
            reply = self.run_light("turn on the mood lights", "unverified")
        self.assertEqual(reply, "I couldn't turn on Mood Lights.")

    def test_unavailable_light_is_short(self):
        self.ha.entities["light.mood_lights"]["state"] = "unavailable"
        reply = self.run_light("turn on the mood lights", "unavailable")
        self.assertEqual(reply, "I couldn't turn on Mood Lights.")

    def test_partial_lists_only_what_failed(self):
        self.ha.entities["light.mood_lights"]["state"] = "unavailable"
        reply = self.run_light("turn on the study light and the mood lights", "partial")
        self.assertEqual(reply, "I couldn't turn on Mood Lights.")
        self.assertEqual(self.ha.entities["light.study_light"]["state"], "on")

    def test_brightness_still_says_the_level(self):
        reply = self.run_light("set the bedroom lamp to 30 percent", "confirmed")
        self.assertIn("30%", reply)
