"""Operational GET route regression tests."""
import json
import unittest
from types import SimpleNamespace
import operational_read_routes


class Handler:
    def __init__(self, path):
        self.path = path
        self.result = None

    def send_json(self, status, payload):
        self.result = (status, payload)

    def send_body(self, status, data, content_type, filename):
        self.result = (status, json.loads(data), content_type, filename)


class OperationalReadTests(unittest.TestCase):
    def setUp(self):
        self.updates = SimpleNamespace(
            status_result=lambda: SimpleNamespace(to_wire=lambda: {"state": "idle"}),
            check=lambda: ["1.0"])
        self.config = SimpleNamespace(export=lambda learning=False: {"learning": learning},
                                      recovery=lambda learning=False: {"recovery": learning})

    def run_route(self, path):
        handler = Handler(path)
        operational_read_routes.dispatch(
            handler, ha_status=lambda: SimpleNamespace(status=SimpleNamespace(value="connected")),
            release_version="1.2", updates=self.updates, configuration=self.config)
        return handler.result

    def test_exact_allowlist(self):
        self.assertEqual(len(operational_read_routes.ROUTES), 7)
        self.assertFalse(operational_read_routes.handles("/api/settings/import"))
        with self.assertRaises(ValueError):
            self.run_route("/api/settings/import")

    def test_status_and_update_failure(self):
        self.assertEqual(self.run_route("/api/ha-status"),
                         (200, {"status": "connected", "release_version": "1.2"}))
        self.assertEqual(self.run_route("/api/updates/status"),
                         (200, {"state": "idle", "current": "1.2"}))
        self.assertEqual(self.run_route("/api/updates")[1]["versions"], ["1.0"])
        self.updates.check = lambda: (_ for _ in ()).throw(OSError())
        self.assertEqual(self.run_route("/api/updates")[0], 503)

    def test_exports_and_failure(self):
        for path, expected in (
            ("/api/settings/export", {"learning": False}),
            ("/api/settings/export-learning", {"learning": True}),
            ("/api/settings/recovery", {"recovery": False}),
            ("/api/settings/recovery-learning", {"recovery": True}),
        ):
            result = self.run_route(path)
            self.assertEqual(result, (200, expected, "application/json",
                                      "declan-settings.json"))
        self.config.export = lambda learning=False: (_ for _ in ()).throw(ValueError())
        self.assertEqual(self.run_route("/api/settings/export")[0], 503)


if __name__ == "__main__":
    unittest.main()
