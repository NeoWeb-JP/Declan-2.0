"""Dependency readiness checks preserve the existing lightweight health contract."""
import unittest
from pathlib import Path
from unittest.mock import patch

import server


class HealthDependencyEndpointTests(unittest.TestCase):
    def test_existing_health_endpoint_remains_lightweight(self):
        # Startup health remains independent of external Home Assistant availability.
        source = __import__("inspect").getsource(server)
        self.assertIn('http_handler_adapters.do_GET(', source)
        self.assertIn('get_request_dispatch.dispatch(', (__import__("pathlib").Path(__file__).resolve().parents[1] / "declan/http/http_handler_adapters.py").read_text())
        self.assertIn('system_read_routes.handles(handler.path)', (Path(__file__).resolve().parents[1] / 'declan/http/get_request_dispatch.py').read_text())
        routes = __import__("inspect").getsource(__import__("declan.http.system_read_routes", fromlist=["x"]))
        self.assertIn('path == "/health"', routes)
        self.assertIn('path == "/health/dependencies"', routes)

    def test_home_assistant_status_returns_not_configured_without_credentials(self):
        with patch.dict(server.os.environ, {"DECLAN_HA_URL": "", "DECLAN_HA_TOKEN": ""}):
            with patch.object(server.history, "has_recent_assist", return_value=False):
                self.assertEqual(server.home_assistant_status(), "not_configured")


if __name__ == "__main__":
    unittest.main()
