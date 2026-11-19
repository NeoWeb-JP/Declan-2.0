"""Guest assignment command parsing regression tests."""
import unittest
from declan.turn.guest_assignment_command import assignment_action


class GuestAssignmentCommandTests(unittest.TestCase):
    def setUp(self):
        self.commands = {"guests have left": "clear", "who is in charge": "status"}

    def test_configured_clear_command(self):
        self.assertEqual(assignment_action("guests have left", self.commands), "clear")

    def test_configured_status_command(self):
        self.assertEqual(assignment_action("who is in charge", self.commands), "status")

    def test_configured_command_takes_priority(self):
        commands = {"mike is in charge": "custom"}
        self.assertEqual(assignment_action("mike is in charge", commands), "custom")

    def test_simple_named_assignment(self):
        self.assertEqual(assignment_action("mike is in charge", self.commands), "assign:mike")

    def test_multiple_guests(self):
        self.assertEqual(assignment_action("mike and kathy are in charge", self.commands),
                         "assign:mike and kathy")

    def test_we_are_going_out_prefix(self):
        self.assertEqual(assignment_action("we are going out and mike is in charge", self.commands),
                         "assign:mike")

    def test_were_going_out_prefix(self):
        self.assertEqual(assignment_action("we're going out and kathy is in charge", self.commands),
                         "assign:kathy")

    def test_set_prefix_and_house_suffix(self):
        self.assertEqual(assignment_action("set mike and kathy are in charge of the house", self.commands),
                         "assign:mike and kathy")

    def test_make_prefix(self):
        self.assertEqual(assignment_action("make mike is in charge", self.commands), "assign:mike")

    def test_put_prefix(self):
        self.assertEqual(assignment_action("put mike is in charge", self.commands), "assign:mike")

    def test_unrelated_command(self):
        self.assertIsNone(assignment_action("turn on the kitchen light", self.commands))

    def test_partial_phrase_rejected(self):
        self.assertIsNone(assignment_action("please mike is in charge now", self.commands))

    def test_empty_phrase_rejected(self):
        self.assertIsNone(assignment_action("", self.commands))
