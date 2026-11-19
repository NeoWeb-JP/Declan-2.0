"""Roast and guest command dispatch regression tests."""
import unittest
from unittest.mock import Mock
from declan.turn.roast_guest_dispatch import dispatch_roast_or_guest


class RoastGuestDispatchTests(unittest.TestCase):
    def setUp(self):
        self.target = Mock(return_value=None)
        self.roast = Mock(return_value=("roasted", "confirmed"))
        self.action = Mock(return_value=None)
        self.assign = Mock(return_value=("assigned", "confirmed"))
        self.connection = Mock(return_value="ha")
        self.args = dict(roast_target=self.target, respond_to_roast=self.roast,
                         guest_mode=Mock(), visitors_present=Mock(),
                         response_guest_mode=Mock(), roast_respond=Mock(),
                         assignment_action=self.action, guest_commands={"guests": "set"},
                         guest_assignment=self.assign, connection=self.connection)

    def run_dispatch(self):
        return dispatch_roast_or_guest("test phrase", **self.args)

    def test_no_match(self):
        self.assertIsNone(self.run_dispatch())

    def test_roast_match(self):
        self.target.return_value = "Edd"
        self.assertEqual(self.run_dispatch(), ("roasted", "confirmed"))

    def test_roast_precedes_guest(self):
        self.target.return_value = "Edd"
        self.action.return_value = "set"
        self.run_dispatch()
        self.action.assert_not_called()

    def test_roast_does_not_open_connection(self):
        self.target.return_value = "Edd"
        self.run_dispatch()
        self.connection.assert_not_called()

    def test_roast_target_forwarded(self):
        self.target.return_value = "Edd"
        self.run_dispatch()
        self.assertEqual(self.roast.call_args.args[0], "Edd")

    def test_roast_guest_mode_callback_forwarded(self):
        self.target.return_value = "Edd"
        self.run_dispatch()
        self.assertIs(self.roast.call_args.kwargs["guest_mode"], self.args["guest_mode"])

    def test_guest_assignment(self):
        self.action.return_value = "set"
        self.assertEqual(self.run_dispatch(), ("assigned", "confirmed"))

    def test_guest_connection_created_once(self):
        self.action.return_value = "set"
        self.run_dispatch()
        self.connection.assert_called_once_with()

    def test_guest_action_forwarded(self):
        self.action.return_value = "clear"
        self.run_dispatch()
        self.assign.assert_called_once_with("clear", "ha")

    def test_guest_commands_forwarded(self):
        self.run_dispatch()
        self.assertIs(self.action.call_args.args[1], self.args["guest_commands"])

    def test_no_match_skips_connection(self):
        self.run_dispatch()
        self.connection.assert_not_called()

    def test_guest_error_propagates(self):
        self.action.return_value = "set"
        self.assign.side_effect = ValueError("unavailable")
        with self.assertRaises(ValueError):
            self.run_dispatch()
