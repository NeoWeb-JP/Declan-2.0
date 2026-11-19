"""Stop-all provider uses typed core while preserving legacy public responses."""
import unittest
from unittest.mock import patch

import server
from declan.core.execution_results import ExecutionResult, Outcome


class TypedStopEverywhereProviderTests(unittest.TestCase):
    def test_typed_stop_result_preserves_diagnostics(self):
        with patch.object(server, "_stop_everywhere_typed_core",
                          return_value=(ExecutionResult("", Outcome.PARTIAL), "One player still active")):
            typed, status = server.stop_everywhere_result(None)
        self.assertIs(typed.outcome, Outcome.PARTIAL)
        self.assertEqual(status, "One player still active")

    def test_unconfigured_stop_is_typed(self):
        typed, status = server.stop_everywhere_result(None)
        self.assertIs(typed.outcome, Outcome.NOT_CONFIGURED)
        self.assertEqual(status, "Home Assistant is not configured.")

    def test_invalid_provider_outcome_is_rejected(self):
        with patch.object(server, 'read_music_inventory_result',
                          return_value=([], "not_an_outcome")):
            with self.assertRaises(ValueError):
                server.stop_everywhere_result("connection")

    def test_legacy_public_response_remains_triple(self):
        self.assertEqual(server.stop_everywhere_output(None),
                         ("", "not_configured", "Home Assistant is not configured."))


if __name__ == "__main__":
    unittest.main()
