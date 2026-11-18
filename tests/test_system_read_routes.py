"""Regression coverage for system GET routes."""
import unittest
from pathlib import Path
from types import SimpleNamespace
import system_read_routes


class Handler:
    def __init__(self, path):
        self.path = path
        self.response = None

    def send_json(self, status, payload):
        self.response = (status, payload)

    def send_body(self, status, payload, content_type):
        self.response = (status, payload, content_type)


class SystemReadTests(unittest.TestCase):
    def setUp(self):
        class Health:
            def response(self):
                return 503, {"status": "degraded"}
        self.health = SimpleNamespace(
            database_health_response=lambda: (200, {"status": "ok"}),
            database_ready=lambda: False,
            DependencyHealth=lambda **kwargs: Health(),
        )

    def run_route(self, path):
        handler = Handler(path)
        system_read_routes.dispatch(
            handler, logo_path=Path(__file__),
            health_readiness=self.health, ha_status=lambda: "disconnected",
            release_version="1.2",
        )
        return handler.response

    def test_allowlist_and_unknown(self):
        self.assertEqual(len(system_read_routes.ROUTES), 5)
        self.assertFalse(system_read_routes.handles("/api/assist"))
        with self.assertRaises(ValueError):
            self.run_route("/api/assist")

    def test_health_contracts(self):
        self.assertEqual(self.run_route("/health"), (200, {"status": "ok"}))
        self.assertEqual(self.run_route("/health/dependencies"),
                         (503, {"status": "degraded"}))

    def test_capabilities_and_static_responses(self):
        self.assertEqual(self.run_route("/")[0], 404)
        self.assertEqual(self.run_route("/api/capabilities")[1],
                         {"api_version": "1.0", "server_version": "1.2",
                          "capabilities": ["updates", "ha_status"]})
        result = self.run_route("/logo.png")
        self.assertEqual(result[0], 200)
        self.assertEqual(result[2], "image/png")
        self.assertTrue(result[1])


if __name__ == "__main__":
    unittest.main()
