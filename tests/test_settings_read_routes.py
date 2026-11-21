"""Regression tests for settings GET dispatch."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from declan.http import settings_read_routes


class Handler:
    def __init__(self, path):
        self.path = path
        self.response = None
        self.spotify_settings = MagicMock()
        self.approved_player_settings = MagicMock()

    def send_json(self, status, payload):
        self.response = status, payload


class SettingsReadTests(unittest.TestCase):
    def setUp(self):
        self.pipeline = SimpleNamespace(PipelineError=type("PipelineError", (Exception,), {}),
                                        listing=lambda: {"matches": []})
        self.profiles = SimpleNamespace(listing=lambda: ["profile"])
        self.diagnostics = SimpleNamespace(recent=lambda: ["trace"])
        self.history = SimpleNamespace(database=lambda: DummyDatabase())
        self.budget = SimpleNamespace(monthly_reserved=lambda db: 100)
        self.ai_settings = SimpleNamespace(read=lambda: {"enabled": True})
        self.ai_credentials = SimpleNamespace(configured=lambda: True)
        self.playlists = SimpleNamespace(listing=lambda: ["country"])

    def run_route(self, path):
        h = Handler(path)
        settings_read_routes.dispatch(
            h, voicepipeline=self.pipeline, voice_profiles=self.profiles,
            diagnostics=self.diagnostics, history=self.history,
            ai_budget=self.budget, ai_settings=self.ai_settings,
            ai_credentials=self.ai_credentials, spotify_playlists=self.playlists)
        return h

    def test_allowlist_and_delegation(self):
        self.assertEqual(len(settings_read_routes.ROUTES), 13)
        self.assertFalse(settings_read_routes.handles("/api/settings/import"))
        with self.assertRaises(ValueError):
            self.run_route("/api/settings/import")
        self.run_route("/api/settings/spotify").spotify_settings.assert_called_once_with()
        self.run_route("/api/settings/media-players").approved_player_settings.assert_called_once_with()

    def test_voice_and_diagnostics(self):
        self.assertEqual(self.run_route("/api/voicepipeline").response, (200, {"matches": []}))
        self.assertEqual(self.run_route("/api/voice-profiles").response, (200, ["profile"]))
        self.assertEqual(self.run_route("/api/diagnostics").response, (200, {"traces": ["trace"]}))
        self.profiles.listing = lambda: (_ for _ in ()).throw(OSError())
        self.assertEqual(self.run_route("/api/voice-profiles").response[0], 503)
        self.diagnostics.recent = lambda: (_ for _ in ()).throw(ValueError())
        self.assertEqual(self.run_route("/api/diagnostics").response[0], 503)

    def test_ai_and_playlists(self):
        self.assertEqual(self.run_route("/api/settings/ai").response,
                         (200, {"settings": {"enabled": True}, "key_configured": True,
                                "month_usage_micro_usd": 100}))
        self.assertEqual(self.run_route("/api/settings/music-playlists").response,
                         (200, ["country"]))
        self.playlists.listing = lambda: (_ for _ in ()).throw(OSError())
        self.assertEqual(self.run_route("/api/settings/music-playlists").response[0], 503)


class DummyDatabase:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


if __name__ == "__main__":
    unittest.main()
