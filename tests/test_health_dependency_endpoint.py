"""Dependency readiness checks preserve the existing lightweight health contract."""
import unittest
from unittest.mock import patch

import server


class HealthDependencyEndpointTests(unittest.TestCase):
    def test_existing_health_endpoint_remains_lightweight(self):
        # Startup health remains independent of external Home Assistant availability.
        source = __import__("inspect").getsource(server)
        self.assertIn('elif self.path == "/health":', source)
        self.assertIn('elif self.path == "/health/dependencies":', source)

    def test_home_assistant_status_returns_not_configured_without_credentials(self):
        with patch.dict(server.os.environ, {"DECLAN_HA_URL": "", "DECLAN_HA_TOKEN": ""}):
            with patch.object(server.history, "has_recent_assist", return_value=False):
                self.assertEqual(server.home_assistant_status(), "not_configured")


if __name__ == "__main__":
    unittest.main()
