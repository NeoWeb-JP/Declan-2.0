"""Database-only health response preserves the existing startup probe contract."""
import unittest
from unittest.mock import patch

import health_readiness


class DatabaseHealthResponseTests(unittest.TestCase):
    def test_healthy_database_response(self):
        with patch.object(health_readiness, "database_ready", return_value=True) as probe:
            self.assertEqual(health_readiness.database_health_response(), (200, {"status": "ok"}))
        probe.assert_called_once_with()

    def test_unavailable_database_response(self):
        with patch.object(health_readiness, "database_ready", return_value=False) as probe:
            self.assertEqual(health_readiness.database_health_response(),
                             (503, {"status": "unavailable"}))
        probe.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
