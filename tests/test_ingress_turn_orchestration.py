"""Regression tests for grouped ingress turn stages."""
import unittest
from unittest.mock import Mock

from sensitive_confirmation_resolution import (
    resolve_confirmation,
)


class IngressTurnOrchestrationTests(unittest.TestCase):
    def test_confirmation_resolves_once_with_original_phrase(self):
        confirm = Mock(return_value="decision")
        resolve = Mock(return_value=("new-session", "yes", "yes", {"reply": "ok"}))
        deps = {name: Mock() for name in (
            "evaluate", "confirmation_response", "normalize", "record",
            "diagnostic_id", "log_error",
        )}
        result = resolve_confirmation(
            "yes", "original", "session", confirm=confirm, resolve=resolve,
            source="assist", satellite="sat", origin_device="kitchen",
            speaker="speaker", guest_commands={"guest"}, confirmations={},
            effective_message="original", **deps,
        )
        self.assertEqual(result[0], "new-session")
        confirm.assert_called_once_with(
            "yes", "original", "session", source="assist", satellite="sat",
            origin_device="kitchen", speaker="speaker",
            guest_commands={"guest"}, confirmations={}, **deps,
        )
        resolve.assert_called_once_with("decision", "original", "original")


if __name__ == "__main__":
    unittest.main()
