"""Roast command response policy regression tests."""
import unittest
from unittest.mock import Mock
from declan.turn.roast_command_dispatch import respond_to_roast


class RoastCommandDispatchTests(unittest.TestCase):
    def setUp(self):
        self.guest_mode = Mock(return_value=False)
        self.visitors_present = Mock(return_value=False)
        self.response_guest_mode = Mock(return_value="off")
        self.respond = Mock(return_value="Try harder.")

    def dispatch(self, target="edd"):
        return respond_to_roast(target, guest_mode=self.guest_mode,
            visitors_present=self.visitors_present,
            response_guest_mode=self.response_guest_mode, respond=self.respond)

    def test_roast_response_is_confirmed(self):
        self.assertEqual(self.dispatch(), ("Try harder.", "confirmed"))

    def test_off_mode_disables_guest_roast(self):
        self.dispatch()
        self.respond.assert_called_once_with("edd", guest=False)

    def test_guest_mode_enables_guest_roast(self):
        self.response_guest_mode.return_value = "guest"
        self.dispatch()
        self.respond.assert_called_once_with("edd", guest=True)

    def test_non_off_mode_enables_guest_roast(self):
        self.response_guest_mode.return_value = "home"
        self.dispatch()
        self.respond.assert_called_once_with("edd", guest=True)

    def test_guest_mode_and_visitors_are_consulted(self):
        self.guest_mode.return_value = True
        self.visitors_present.return_value = True
        self.dispatch()
        self.response_guest_mode.assert_called_once_with(True, True)

    def test_target_passed_without_modification(self):
        self.dispatch("jaco")
        self.respond.assert_called_once_with("jaco", guest=False)

    def test_policy_called_once(self):
        self.dispatch()
        self.response_guest_mode.assert_called_once()

    def test_guest_mode_reader_called_once(self):
        self.dispatch()
        self.guest_mode.assert_called_once()

    def test_visitors_reader_called_once(self):
        self.dispatch()
        self.visitors_present.assert_called_once()
