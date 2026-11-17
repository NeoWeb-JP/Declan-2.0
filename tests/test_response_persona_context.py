"""Response persona context regression tests."""
import unittest
from unittest.mock import Mock
from response_persona_context import resolve_response_persona


class ResponsePersonaContextTests(unittest.TestCase):
    def setUp(self):
        self.read_guest = Mock(return_value="off")
        self.read_visitors = Mock(return_value=False)
        self.policy = Mock()
        self.policy.response_guest_mode.return_value = "off"

    def resolve(self):
        return resolve_response_persona(self.read_guest, self.read_visitors, self.policy)

    def test_returns_all_three_values(self):
        self.assertEqual(self.resolve(), ("off", False, "off"))

    def test_guest_mode_forwarded_to_policy(self):
        self.read_guest.return_value = "on"
        self.resolve()
        self.policy.response_guest_mode.assert_called_once_with("on", False)

    def test_visitor_presence_forwarded_to_policy(self):
        self.read_visitors.return_value = True
        self.resolve()
        self.policy.response_guest_mode.assert_called_once_with("off", True)

    def test_unknown_presence_forwarded_to_policy(self):
        self.read_visitors.return_value = None
        self.resolve()
        self.policy.response_guest_mode.assert_called_once_with("off", None)

    def test_response_mode_from_policy_preserved(self):
        self.policy.response_guest_mode.return_value = "guest"
        self.assertEqual(self.resolve()[2], "guest")

    def test_explicit_guest_mode_preserved_independently(self):
        self.read_guest.return_value = "on"
        self.policy.response_guest_mode.return_value = "guest"
        self.assertEqual(self.resolve(), ("on", False, "guest"))

    def test_read_guest_called_once(self):
        self.resolve()
        self.read_guest.assert_called_once_with()

    def test_read_visitors_called_once(self):
        self.resolve()
        self.read_visitors.assert_called_once_with()

    def test_policy_called_once(self):
        self.resolve()
        self.policy.response_guest_mode.assert_called_once()
