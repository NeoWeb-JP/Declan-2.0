"""On-demand roast parsing and Guest Mode tone coverage."""
import unittest
from unittest.mock import patch

from declan.turn import roast
import server


class RoastTests(unittest.TestCase):
    def test_supported_commands(self):
        self.assertEqual(roast.target("roast me"), "you")
        self.assertEqual(roast.target("please roast me"), "you")
        self.assertEqual(roast.target("roast Edd"), "Edd")
        self.assertEqual(roast.target("roast Mike"), "Mike")
        self.assertEqual(roast.target("roast Kathy"), "Kathy")

    def test_other_commands_are_not_intercepted(self):
        for phrase in ("who is in charge", "roast", "roast 123", "roast <script>"):
            self.assertIsNone(roast.target(phrase))

    def test_guest_mode_uses_only_guest_lines(self):
        with patch.object(roast._RANDOM, "choice", side_effect=lambda lines: lines[0]) as choose:
            self.assertIn("Edd", roast.respond("Edd", guest=True))
            self.assertIs(choose.call_args.args[0], roast.GUEST)
            self.assertIn("Edd", roast.respond("Edd", guest=False))
            self.assertIs(choose.call_args.args[0], roast.HOME)

    def test_guest_policy_does_not_toggle_guest_mode(self):
        with patch.object(server, "read_guest_mode", return_value="on"):
            mode = server.personality_policy.response_guest_mode(server.read_guest_mode(), False)
        self.assertEqual(mode, "on")


if __name__ == "__main__":
    unittest.main()
