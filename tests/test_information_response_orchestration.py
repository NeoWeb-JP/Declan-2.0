"""Information dispatch response regressions."""

import unittest
from unittest.mock import Mock

from information_response_orchestration import dispatch_information_response


class InformationResponseOrchestrationTests(unittest.TestCase):
    def test_adapts_matched_information_command(self):
        dispatch = Mock(return_value="information")
        adapt = Mock(return_value="response")
        dependencies = {
            name: Mock() for name in (
                "registry_factory", "context_factory", "matches", "follow_up",
                "handle", "question_context", "decorate", "guest_mode",
            )
        }
        result = dispatch_information_response(
            "what is the weather", source="assist", dispatch=dispatch,
            adapt=adapt, opener="opener", last_information="previous",
            **dependencies,
        )
        self.assertEqual(result, "response")
        adapt.assert_called_once_with("information")
        dispatch.assert_called_once_with(
            "what is the weather", source="assist", opener="opener",
            last_information="previous", **dependencies,
        )

    def test_unmatched_information_falls_through(self):
        adapt = Mock()
        dependencies = {
            name: Mock() for name in (
                "registry_factory", "context_factory", "matches", "follow_up",
                "handle", "question_context", "decorate", "guest_mode",
            )
        }
        result = dispatch_information_response(
            "lights on", source="chat", dispatch=Mock(return_value=None),
            adapt=adapt, opener=None, last_information=None, **dependencies,
        )
        self.assertIsNone(result)
        adapt.assert_not_called()


if __name__ == "__main__":
    unittest.main()
