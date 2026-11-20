"""Volume ("turn it up", "volume to 30%") and brightness percentage wording."""
import unittest
from unittest.mock import Mock, patch

from declan.ai import conversation_agent
from declan.core.execution_results import ExecutionResult, Outcome
from declan.ha import lighting_intents
from declan.ha.light_command_parsing import parse_light_command
from declan.music import music
from declan.timers import timers


class VolumeParsingTests(unittest.TestCase):
    def test_relative_and_absolute_volume(self):
        cases = {
            "turn it up": ("volume_up", None), "turn it down please": ("volume_down", None),
            "turn the music up in the kitchen": ("volume_up", "kitchen"), "turn up the volume": ("volume_up", None),
            "volume down": ("volume_down", None), "louder": ("volume_up", None), "make it quieter": ("volume_down", None),
            "turn the volume down everywhere": ("volume_down", "everywhere"),
            "set the volume to 30 percent": ("volume_set_30", None), "set the volume to 30%": ("volume_set_30", None),
            "set the volume in the kitchen to 25 percent": ("volume_set_25", "kitchen"),
            "volume 40": ("volume_set_40", None),
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(music.parse_control(phrase), expected)

    def test_not_volume(self):
        for phrase in ("volume to 120", "turn up the lights", "make it brighter", "turn it on", "turn the music to 40 percent"):
            with self.subTest(phrase=phrase):
                self.assertIsNone(music.parse_volume(phrase))
        self.assertEqual(music.parse_control("pause"), ("media_pause", None))


class VolumeExecutionTests(unittest.TestCase):
    def run_volume(self, action, level, *, reaches=True):
        player = {"state": "playing", "attributes": {} if level is None else {"volume_level": level}}
        with patch.object(music, "request") as request, \
                patch.object(music, "wait_for", return_value=reaches) as wait:
            result = music._volume_result(("u", {}, None), "media_player.kitchen", player, action, "in the kitchen")
        return result, request, wait

    def test_steps_and_sets_with_verification(self):
        result, request, _ = self.run_volume("volume_up", 0.4)
        self.assertEqual((result.reply, result.outcome), ("Turned it up to 50% in the kitchen.", Outcome.CONFIRMED))
        self.assertEqual(request.call_args.args[1:], ("/api/services/media_player/volume_set",
                                                       {"entity_id": "media_player.kitchen", "volume_level": 0.5}))
        result, request, _ = self.run_volume("volume_set_30", 0.8)
        self.assertEqual(result.reply, "Volume set to 30% in the kitchen.")
        result, _, _ = self.run_volume("volume_down", 0.05)
        self.assertEqual(result.reply, "Turned it down to 0% in the kitchen.")

    def test_already_unverified_and_unknown_level(self):
        result, request, _ = self.run_volume("volume_set_40", 0.4)
        self.assertEqual((result.outcome, request.called), (Outcome.CONFIRMED, False))
        result, _, _ = self.run_volume("volume_up", 0.4, reaches=False)
        self.assertEqual(result.outcome, Outcome.UNVERIFIED)
        result, request, _ = self.run_volume("volume_down", None)
        self.assertEqual(result.outcome, Outcome.REQUESTED)
        self.assertEqual(request.call_args.args[1], "/api/services/media_player/volume_down")


class BrightnessTests(unittest.TestCase):
    def test_loose_percentage_wording_is_canonical(self):
        cases = {
            "turn the kitchen lights to 40%": "set the kitchen lights to 40 percent",
            "put the lamp at 30 percent": "set the lamp to 30 percent",
            "kitchen lights 50 percent": "set the kitchen lights to 50 percent",
            "brightness to 40 percent in the kitchen": "set the lights in the kitchen to 40 percent",
            "set the brightness in the office to 70%": "set the lights in the office to 70 percent",
            "lights to 30 percent in here": "set the lights to 30 percent in here",
            "set the kitchen lights to 30 percent": "set the kitchen lights to 30 percent",
            "set the volume to 30 percent": "set the volume to 30 percent",
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(lighting_intents.canonical_brightness(phrase), expected)
        self.assertFalse(lighting_intents.matches("set the volume to 30 percent", parse_light_command))
        self.assertTrue(lighting_intents.matches("kitchen lights 50 percent", parse_light_command))

    def handle(self, phrase, origin="device-1"):
        set_lights = Mock(return_value=ExecutionResult("Done.", Outcome.CONFIRMED))
        result = lighting_intents.handle_light_request_result(
            phrase, parse_light_command=parse_light_command, set_lights=set_lights, origin_device=origin)
        return result, set_lights

    def test_percent_in_here_uses_the_speakers_room(self):
        result, set_lights = self.handle("lights to 30 percent in here")
        self.assertEqual(result.outcome, Outcome.CONFIRMED)
        self.assertEqual(set_lights.call_args.args, ("lights", "on"))
        self.assertEqual((set_lights.call_args.kwargs["brightness"], set_lights.call_args.kwargs["origin_device"]),
                         (30, "device-1"))
        result, set_lights = self.handle("set the lights to 40 percent in here", origin=None)
        self.assertEqual(result.outcome, Outcome.UNRESOLVED)
        set_lights.assert_not_called()

    def test_named_light_percentage(self):
        _, set_lights = self.handle("turn the kitchen lights to 40%")
        self.assertEqual(set_lights.call_args.args, ("kitchen lights", "on"))
        self.assertEqual(set_lights.call_args.kwargs["brightness"], 40)


class AgentCommandTests(unittest.TestCase):
    def test_agent_may_issue_brightness_and_volume_commands(self):
        checks = (lambda p: lighting_intents.matches(p, parse_light_command), lambda p: music.parse(p) is not None,
                  lambda p: music.parse_control(p) is not None, timers.matches)
        for command in ("set the kitchen lights to 40 percent", "turn the music up", "turn the music down in the kitchen",
                        "set the volume to 30 percent", "set the volume to 30 percent in the kitchen"):
            with self.subTest(command=command):
                self.assertEqual(conversation_agent.valid_command(command, routines=set(), checks=checks), command)
        self.assertIsNone(conversation_agent.valid_command("set the volume to loud percent", routines=set(), checks=checks))
        self.assertIn("set the volume to <n> percent", conversation_agent.INSTRUCTIONS)


if __name__ == "__main__":
    unittest.main()
