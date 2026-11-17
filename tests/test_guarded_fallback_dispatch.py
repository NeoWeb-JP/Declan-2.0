"""Guarded fallback dispatch regression tests."""
import unittest
from unittest.mock import Mock
from guarded_fallback_dispatch import dispatch_fallback


class GuardedFallbackDispatchTests(unittest.TestCase):
    def setUp(self):
        self.handler = Mock(return_value=("Done", "confirmed", [{"action": "light.on"}]))
        self.actions = [{"action": "prior"}]
        self.exposed = ["light.kitchen"]

    def dispatch(self, message="turn on the light", source="assist"):
        return dispatch_fallback(message, source=source, exposed_entities=self.exposed,
            fallback_handler=self.handler, action_results=self.actions)

    def test_reply_and_outcome(self):
        self.assertEqual(self.dispatch(), ("Done", "confirmed"))

    def test_fallback_steps_appended(self):
        self.dispatch()
        self.assertEqual(self.actions, [{"action": "prior"}, {"action": "light.on"}])

    def test_no_fallback_returns_none(self):
        self.handler.return_value = None
        self.assertIsNone(self.dispatch())

    def test_no_fallback_preserves_actions(self):
        self.handler.return_value = None
        self.dispatch()
        self.assertEqual(self.actions, [{"action": "prior"}])

    def test_message_forwarded(self):
        self.dispatch("dim the lights")
        self.assertEqual(self.handler.call_args.args, ("dim the lights",))

    def test_source_forwarded(self):
        self.dispatch(source="browser")
        self.assertEqual(self.handler.call_args.kwargs["source"], "browser")

    def test_exposure_passed_by_reference(self):
        self.dispatch()
        self.assertIs(self.handler.call_args.kwargs["exposed_entities"], self.exposed)

    def test_empty_fallback_steps(self):
        self.handler.return_value = ("No action", "unmatched", [])
        self.assertEqual(self.dispatch(), ("No action", "unmatched"))
        self.assertEqual(self.actions, [{"action": "prior"}])

    def test_failed_outcome_preserved(self):
        self.handler.return_value = ("Failed", "failed", [{"status": "failed"}])
        self.assertEqual(self.dispatch(), ("Failed", "failed"))

    def test_handler_called_once(self):
        self.dispatch()
        self.handler.assert_called_once()
