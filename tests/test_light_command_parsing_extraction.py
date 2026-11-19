"""Regression coverage for extracted multi-clause lighting parser."""
import unittest
from unittest.mock import patch

import light_command_parsing
import server


class LightCommandParsingExtractionTests(unittest.TestCase):
    def test_server_wrapper_uses_extracted_parser(self):
        with patch.object(light_command_parsing, "parse_light_command", return_value=("desk", "on")) as parser:
            self.assertEqual(server.parse_light_command("turn on desk"), ("desk", "on"))
        parser.assert_called_once_with("turn on desk")

    def test_simple_and_relative_commands(self):
        cases = {
            "turn on the kitchen": ("kitchen", "on"),
            "turn the kitchen off": ("kitchen", "off"),
            "dim the lounge": ("lounge", "darker"),
            "brighten the lounge": ("lounge", "brighter"),
            "make the lounge lighter": ("lounge", "brighter"),
            "turn everything off except the kitchen": ("everything except kitchen", "off"),
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(light_command_parsing.parse_light_command(phrase), expected)

    def test_invalid_command_is_not_dispatched(self):
        self.assertIsNone(light_command_parsing.parse_light_command("play some music"))

    def test_chained_commands_preserve_order(self):
        self.assertEqual(
            light_command_parsing.parse_light_command("turn on kitchen and then turn off lounge"),
            ("kitchen and turn off lounge", "on"),
        )


if __name__ == "__main__":
    unittest.main()
