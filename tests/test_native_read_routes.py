"""Regression tests for extracted native read-only routes."""
import unittest
from types import SimpleNamespace
import native_read_routes


class Handler:
    def __init__(self, path):
        self.path = path
        self.sent = []

    def send_json(self, status, body):
        self.sent.append((status, body))


class NativeReadTests(unittest.TestCase):
    def setUp(self):
        self.discovery = SimpleNamespace(error=None, scripts=[
            {"entity_id": "script.good_morning", "name": "Good Morning"}])
        self.config = SimpleNamespace(export=lambda: {"export": 1},
                                      recovery=lambda: {"recovery": 2})
        self.music = SimpleNamespace(spotify_credentials=lambda: (None, "saved"))
        self.history = SimpleNamespace(learned_intents=lambda: ["hello"])
        self.logs = SimpleNamespace(recent=lambda: ["log"])
        self.diagnostics = SimpleNamespace(recent=lambda: ["trace"])

    def run_route(self, path):
        handler = Handler(path)
        native_read_routes.dispatch(
            handler, music=self.music, configuration=self.config,
            script_discovery=SimpleNamespace(discover_result=lambda *a, **k: self.discovery),
            ha_connection=lambda: object(),
            command_responses=SimpleNamespace(catalog=lambda: ["command"]),
            history=self.history, logs=self.logs, diagnostics=self.diagnostics,
        )
        return handler.sent[0]

    def test_exact_allowlist(self):
        self.assertEqual(len(native_read_routes.ROUTES), 8)
        self.assertFalse(native_read_routes.handles("/api/native/settings-import"))
        self.assertFalse(native_read_routes.handles("/api/native/logs/"))
        with self.assertRaises(ValueError):
            self.run_route("/api/native/settings-import")

    def test_settings_read_and_recovery(self):
        self.assertEqual(self.run_route("/api/native/settings-status"),
                         (200, {"spotify_configured": True, "spotify_source": "saved"}))
        self.assertEqual(self.run_route("/api/native/settings-export"),
                         (200, {"document": {"export": 1}}))
        self.assertEqual(self.run_route("/api/native/settings-recovery"),
                         (200, {"document": {"recovery": 2}}))
        self.config.export = lambda: (_ for _ in ()).throw(OSError())
        self.assertEqual(self.run_route("/api/native/settings-export")[0], 503)

    def test_routine_and_training_reads(self):
        status, body = self.run_route("/api/native/routine-responses")
        self.assertEqual(status, 200)
        self.assertEqual(body["routines"][0]["entity_id"], "script.good_morning")
        self.discovery.error = "offline"
        self.assertIn("routine_error", self.run_route("/api/native/routine-responses")[1])
        self.assertEqual(self.run_route("/api/native/routines")[0], 410)
        self.assertEqual(self.run_route("/api/native/intents"),
                         (200, {"intents": ["hello"]}))
        self.history.learned_intents = lambda: (_ for _ in ()).throw(OSError())
        self.assertEqual(self.run_route("/api/native/intents")[0], 503)

    def test_logs_diagnostics_and_failures(self):
        self.assertEqual(self.run_route("/api/native/logs"), (200, {"entries": ["log"]}))
        self.assertEqual(self.run_route("/api/native/diagnostics"),
                         (200, {"traces": ["trace"]}))
        self.diagnostics.recent = lambda: (_ for _ in ()).throw(ValueError())
        self.assertEqual(self.run_route("/api/native/diagnostics")[0], 503)


if __name__ == "__main__":
    unittest.main()
