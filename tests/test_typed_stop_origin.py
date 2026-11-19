"""Origin-specific stop uses typed results and preserves legacy triples."""
import unittest
from unittest.mock import patch

import server
from declan.core.execution_results import Outcome


class TypedStopOriginTests(unittest.TestCase):
    def test_missing_origin_is_unresolved(self):
        typed, status = server.stop_origin_result(None, None, None)
        self.assertIs(typed.outcome, Outcome.UNRESOLVED)
        self.assertIn("identifiable", status)

    def test_legacy_wrapper_preserves_response(self):
        self.assertEqual(server.stop_origin_output(None, None, None),
                         ("", "unresolved", "Stop needs an identifiable Assist satellite or device."))

    def test_discovery_error_is_typed(self):
        with patch.object(server, 'read_music_inventory_result', return_value=([], "unavailable")):
            typed, status = server.stop_origin_result("connection", "assist_satellite.kitchen", None)
        self.assertIs(typed.outcome, Outcome.UNAVAILABLE)
        self.assertIn("discover", status)

    def test_invalid_discovery_outcome_is_rejected(self):
        with patch.object(server, 'read_music_inventory_result', return_value=([], "invalid_outcome")):
            with self.assertRaises(ValueError):
                server.stop_origin_result("connection", "assist_satellite.kitchen", None)


if __name__ == "__main__":
    unittest.main()
