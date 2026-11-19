"""Bounded operational metrics and authenticated route contract regressions."""

import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from declan.core import diagnostic_metrics
from declan.http import native_read_routes
from declan.http import settings_read_routes


class DiagnosticMetricsTests(unittest.TestCase):
    def test_aggregates_counts_and_latency_without_raw_private_values(self):
        traces = [
            {"route": "/api/assist", "outcome": "confirmed", "duration_ms": 10,
             "message": "private transcript", "token": "secret",
             "stages": [{"stage": "lighting", "outcome": "confirmed", "duration_ms": 3}]},
            {"route": "/api/assist", "outcome": "failed", "duration_ms": 30,
             "stages": [{"stage": "lighting", "outcome": "failed", "duration_ms": 7}]},
            {"route": "/api/chat", "outcome": "unverified", "duration_ms": 20,
             "stages": [{"stage": "speech_generation", "outcome": "failed",
                         "duration_ms": 11}]},
        ]
        result = diagnostic_metrics.aggregate(traces, sampled_at=0)
        self.assertEqual(result["requests"]["/api/assist"],
                         {"count": 2, "errors": 1, "p50_ms": 30, "p95_ms": 30})
        self.assertEqual(result["stages"]["lighting"],
                         {"count": 2, "errors": 1, "p50_ms": 7, "p95_ms": 7})
        self.assertEqual(result["requests"]["/api/chat"]["errors"], 1)
        self.assertNotIn("private transcript", json.dumps(result))
        self.assertNotIn("secret", json.dumps(result))

    def test_unknown_routes_stage_names_and_invalid_durations_are_not_emitted(self):
        traces = [
            {"route": "/api/assist?token=private", "outcome": "failed", "duration_ms": 1},
            {"route": "/api/assist", "outcome": "confirmed",
             "duration_ms": -2, "stages": [
                 {"stage": "speaker-Jaco", "duration_ms": 22},
                 {"stage": "music", "duration_ms": 3},
                 {"stage": "music", "duration_ms": float("nan")},
                 {"stage": "some name with spaces", "duration_ms": 4},
             ]},
            {"route": "/api/assist", "stages": "invalid"},
            {"route": "/api/assist", "duration_ms": None},
        ]
        summary = diagnostic_metrics.aggregate(traces, sampled_at=100)
        self.assertEqual(set(summary["requests"]), {"/api/assist"})
        self.assertEqual(summary["requests"]["/api/assist"]["count"], 3)
        self.assertIsNone(summary["requests"]["/api/assist"]["p50_ms"])
        self.assertEqual(set(summary["stages"]), {"music"})
        self.assertEqual(summary["stages"]["music"]["count"], 2)
        self.assertEqual(summary["stages"]["music"]["p50_ms"], 3)

    def test_sqlite_summary_limits_to_recent_500_traces(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "diagnostics.sqlite"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE traces (id TEXT PRIMARY KEY, created_at REAL, payload TEXT)")
                for n in range(510):
                    db.execute("INSERT INTO traces VALUES (?, ?, ?)",
                               (str(n), float(n), json.dumps({
                                   "route": "/api/stt", "outcome": "completed",
                                   "duration_ms": n})))
                db.execute("INSERT INTO traces VALUES (?, ?, ?)",
                           ("old", -999.0, json.dumps({"route": "/api/chat", "outcome": "failed"})))
            summary = diagnostic_metrics.summary(path, retention=1000, now=510)
            self.assertEqual(summary["requests"]["/api/stt"]["count"], 500)
            self.assertNotIn("/api/chat", summary["requests"])

    def test_missing_database_returns_empty_summary(self):
        with TemporaryDirectory() as folder:
            result = diagnostic_metrics.summary(Path(folder) / "missing.sqlite",
                                                retention=100, now=42)
            self.assertEqual(result["requests"], {})
            self.assertEqual(result["stages"], {})

    def test_native_and_settings_routes_expose_only_aggregate(self):
        self.assertTrue(native_read_routes.handles("/api/native/diagnostics/metrics"))
        self.assertTrue(settings_read_routes.handles("/api/diagnostics/metrics"))
        expected = {"requests": {}, "stages": {}, "sample_limit": 500}
        provider = Mock(metrics=Mock(return_value=expected))
        native = Mock(path="/api/native/diagnostics/metrics")
        native_read_routes.dispatch(native, music=Mock(), configuration=Mock(),
                                    script_discovery=Mock(), ha_connection=Mock(),
                                    command_responses=Mock(), history=Mock(),
                                    logs=Mock(), diagnostics=provider)
        native.send_json.assert_called_once_with(200, {"metrics": expected})
        settings = Mock(path="/api/diagnostics/metrics")
        settings_read_routes.dispatch(settings, voicepipeline=Mock(), voice_profiles=Mock(),
                                      diagnostics=provider, history=Mock(), ai_budget=Mock(),
                                      ai_settings=Mock(), ai_credentials=Mock(),
                                      spotify_playlists=Mock())
        settings.send_json.assert_called_once_with(200, {"metrics": expected})
        self.assertEqual(provider.metrics.call_count, 2)

    def test_metrics_database_failure_is_503(self):
        native = Mock(path="/api/native/diagnostics/metrics")
        provider = Mock(metrics=Mock(side_effect=sqlite3.OperationalError("private")))
        native_read_routes.dispatch(native, music=Mock(), configuration=Mock(),
                                    script_discovery=Mock(), ha_connection=Mock(),
                                    command_responses=Mock(), history=Mock(),
                                    logs=Mock(), diagnostics=provider)
        native.send_json.assert_called_once_with(
            503, {"error": "Diagnostic metrics unavailable."})


if __name__ == "__main__":
    unittest.main()
