"""Stop-all provider exposes typed outcomes without changing legacy callers."""
import unittest
from unittest.mock import patch

import server
from execution_results import Outcome


class TypedStopEverywhereProviderTests(unittest.TestCase):
    def test_typed_stop_result_preserves_diagnostics(self):
        with patch.object(server, "stop_everywhere_output",
                          return_value=("", "partial", "One player still active")):
            typed, status = server.stop_everywhere_result(None)
        self.assertIs(typed.outcome, Outcome.PARTIAL)
        self.assertEqual(status, "One player still active")

    def test_unconfigured_stop_is_typed(self):
        typed, status = server.stop_everywhere_result(None)
        self.assertIs(typed.outcome, Outcome.NOT_CONFIGURED)
        self.assertEqual(status, "Home Assistant is not configured.")

    def test_invalid_provider_outcome_is_rejected(self):
        with patch.object(server, "stop_everywhere_output",
                          return_value=("", "not_an_outcome", None)):
            with self.assertRaises(ValueError):
                server.stop_everywhere_result(None)


if __name__ == "__main__":
    unittest.main()
