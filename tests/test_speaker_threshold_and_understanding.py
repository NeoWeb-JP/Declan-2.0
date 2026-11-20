"""VOI-08 configurable speaker threshold and VOI-12 understanding summary."""
import importlib.util
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from time import time
from types import SimpleNamespace
from unittest.mock import patch

from declan.core import history, understanding_quality
from declan.http import history_read_routes, settings_read_routes
from declan.turn import sensitive_confirmations
from declan.turn.command_vocabulary import UNMATCHED_REPLY
from declan.voice import assist_capture_http, settings_voice_post, speaker_settings

ROOT = Path(__file__).resolve().parents[1]


class Handler:
    def __init__(self, path):
        self.path = path
        self.sent = []

    def send_json(self, status, payload):
        self.sent.append((status, payload))


class SpeakerSettingsTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(TemporaryDirectory())
        self.path = Path(folder) / "speaker-settings.json"
        self.enterContext(patch.object(speaker_settings, "PATH", self.path))
        self.enterContext(patch.dict(os.environ, {}, clear=True))

    def test_default_is_85_and_history_labels_stay_at_75(self):
        self.assertEqual(speaker_settings.listing(), {"threshold": 0.85, "source": "default", "default": 0.85})
        self.assertEqual(speaker_settings.history_threshold(), 0.75)

    def test_saved_beats_environment_beats_default(self):
        with patch.dict(os.environ, {"DECLAN_SPEAKER_THRESHOLD": "0.6"}):
            self.assertEqual(speaker_settings.listing()["source"], "environment")
            self.assertEqual(speaker_settings.threshold(), 0.6)
            saved = speaker_settings.save({"threshold": 0.404})
            self.assertEqual(saved, {"threshold": 0.4, "source": "saved", "default": 0.85})
            self.assertEqual(speaker_settings.history_threshold(), 0.4)

    def test_invalid_values_are_rejected_or_ignored(self):
        for payload in (None, {}, {"threshold": "0.5"}, {"threshold": True}, {"threshold": 0.1},
                        {"threshold": 1.0}, {"threshold": float("nan")}, {"threshold": 0.5, "x": 1}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                speaker_settings.save(payload)
        self.assertFalse(self.path.exists())
        with patch.dict(os.environ, {"DECLAN_SPEAKER_THRESHOLD": "85"}):
            self.assertEqual(speaker_settings.listing()["source"], "default")
        self.path.write_text(json.dumps({"threshold": 5}))
        self.assertEqual(speaker_settings.threshold(), 0.85)

    def test_capture_arbitration_uses_the_setting(self):
        speaker = {"name": "Jaco", "confidence": 0.4}
        self.assertIsNone(assist_capture_http.trusted_speaker_name(speaker))
        speaker_settings.save({"threshold": 0.35})
        self.assertEqual(assist_capture_http.trusted_speaker_name(speaker), "Jaco")

    def test_history_labels_follow_a_lower_setting(self):
        self.assertEqual(history.speaker_match({"name": "Ed", "confidence": 0.4})["name"], "Unknown")
        speaker_settings.save({"threshold": 0.35})
        self.assertEqual(history.speaker_match({"name": "Ed", "confidence": 0.4})["name"], "Ed")

    def test_sensitive_confirmation_keeps_its_fixed_floor(self):
        speaker_settings.save({"threshold": 0.35})
        with patch.dict(os.environ, {"DECLAN_TRUSTED_SPEAKERS": "Jaco"}):
            self.assertFalse(sensitive_confirmations.trusted_speaker({"name": "Jaco", "confidence": 0.5}))
            self.assertTrue(sensitive_confirmations.trusted_speaker({"name": "Jaco", "confidence": 0.9}))

    def test_routes_round_trip(self):
        handler = Handler("/api/settings/speaker")
        self.assertTrue(settings_read_routes.handles(handler.path))
        settings_read_routes.dispatch(handler, voicepipeline=None, voice_profiles=None, diagnostics=None,
                                      history=None, ai_budget=None, ai_settings=None, ai_credentials=None,
                                      spotify_playlists=None)
        self.assertEqual(handler.sent[-1], (200, {"threshold": 0.85, "source": "default", "default": 0.85}))
        self.assertTrue(settings_voice_post.handles(handler.path))
        for body, status in (({"settings": {"threshold": 0.5}}, 200), ({"settings": {"threshold": 2}}, 400),
                             ({"threshold": 0.5}, 400), (None, 400)):
            with self.subTest(body=body):
                settings_voice_post.dispatch(handler, body, **{name: None for name in (
                    "spotify_save", "ai_replace_key", "ai_save", "ai_configured", "music", "spotify_playlists",
                    "playlist_handler", "opener_factory", "voice_manage", "pipeline_error", "profiles_manage",
                    "preview", "apply")})
                self.assertEqual(handler.sent[-1][0], status)
        self.assertEqual(speaker_settings.threshold(), 0.5)

    def test_routes_are_on_every_gate_allowlist(self):
        for module in ("get_access_gate_http", "post_route_gate_http", "post_origin_auth_http"):
            with self.subTest(module=module):
                self.assertIn('"/api/settings/speaker"', (ROOT / "declan/http" / f"{module}.py").read_text())
        self.assertIn('"/api/history/quality"', (ROOT / "declan/http/get_access_gate_http.py").read_text())


class UnderstandingSummaryTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.object(history, "DATABASE", Path(folder) / "conversations.sqlite3"))
        self.enterContext(patch.object(speaker_settings, "PATH", Path(folder) / "speaker-settings.json"))
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.now = time()

    def add(self, age_days, message, reply="Done.", source="assist", outcome=None, confidence=None):
        speaker = None if confidence is None else json.dumps({"name": "Unknown", "confidence": confidence})
        with history.database() as connection:
            connection.execute(
                "INSERT INTO turns(created_at, session_id, source, message, reply, outcome, speaker_match) "
                "VALUES (?, 's', ?, ?, ?, ?, ?)",
                (self.now - age_days * 86400, source, message, reply, outcome, speaker))

    def summary(self):
        with patch.object(history, "time", return_value=self.now):
            return understanding_quality.summary(
                unmatched_reply=UNMATCHED_REPLY, speaker_threshold=0.85, now=self.now)

    def test_weekly_rates_top_phrases_and_speaker_confidence(self):
        self.add(1, "Turn on the office light", confidence=0.3)
        self.add(1, "Blah the thing.", UNMATCHED_REPLY, confidence=0.4)
        self.add(2, "blah the thing", UNMATCHED_REPLY, source="browser_keyboard")
        self.add(2, "dim kitchen", UNMATCHED_REPLY, confidence=0.9)
        self.add(2, "blah the thing", UNMATCHED_REPLY, outcome="duplicate")  # second satellite
        self.add(2, "internal", UNMATCHED_REPLY, source="routine")
        self.add(9, "old miss", UNMATCHED_REPLY)
        self.add(9, "old hit")
        history.teach_phrase("dim kitchen", "dim the kitchen lights")
        result = self.summary()
        self.assertEqual(result["weeks"][0], {"turns": 4, "not_understood": 3, "rate": 0.75})
        self.assertEqual(result["weeks"][1], {"turns": 2, "not_understood": 1, "rate": 0.5})
        self.assertEqual(result["weeks"][2], {"turns": 0, "not_understood": 0, "rate": None})
        self.assertEqual(result["top_not_understood"][0], {"phrase": "blah the thing", "count": 2, "learned": False})
        self.assertIn({"phrase": "dim kitchen", "count": 1, "learned": True}, result["top_not_understood"])
        self.assertIn({"phrase": "old miss", "count": 1, "learned": False}, result["top_not_understood"])
        self.assertEqual(result["speaker"], {"threshold": 0.85, "samples": 3, "median_confidence": 0.4,
                                             "highest_confidence": 0.9, "recognised_share": 0.3333})

    def test_empty_history(self):
        result = self.summary()
        self.assertEqual(len(result["weeks"]), 4)
        self.assertIsNone(result["speaker"]["median_confidence"])
        self.assertEqual(result["top_not_understood"], [])

    def test_route_returns_summary(self):
        self.add(1, "nonsense", UNMATCHED_REPLY)
        handler = Handler("/api/history/quality")
        self.assertTrue(history_read_routes.handles(handler.path))
        history_read_routes.dispatch(handler, history=history)
        status, payload = handler.sent[-1]
        self.assertEqual(status, 200)
        self.assertEqual(payload["weeks"][0]["not_understood"], 1)


class PanelAndViewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        web = SimpleNamespace(json_response=lambda payload, status=200, headers=None:
                              {"payload": payload, "status": status, "headers": headers})
        aiohttp = SimpleNamespace(web=web, ClientTimeout=lambda total: total, ClientError=OSError)
        self.enterContext(patch.dict("sys.modules", {
            "aiohttp": aiohttp, "homeassistant": SimpleNamespace(), "homeassistant.components": SimpleNamespace(),
            "homeassistant.components.http": SimpleNamespace(HomeAssistantView=object),
            "homeassistant.helpers": SimpleNamespace(),
            "homeassistant.helpers.aiohttp_client": SimpleNamespace(async_get_clientsession=lambda hass: None),
        }))
        path = ROOT / "custom_components/declan_two/speaker_settings_view.py"
        spec = importlib.util.spec_from_file_location("speaker_settings_view_fixture", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.view = module.DeclanSpeakerSettingsView()

    def request(self, user, body=None):
        raw = json.dumps(body).encode() if body is not None else b""

        class Request(dict):
            app = {"hass": SimpleNamespace(config_entries=SimpleNamespace(async_entries=lambda domain: []))}
            content_length = len(raw) or None
            content_type = "application/json"

            async def json(self):
                return body
        return Request(hass_user=user)

    async def test_view_is_admin_only_and_validates(self):
        self.assertEqual((await self.view.get(self.request(SimpleNamespace(is_admin=False))))["status"], 403)
        admin = SimpleNamespace(is_admin=True)
        for body in ({"settings": {"threshold": 0.1}}, {"settings": {"threshold": "0.5"}}, [1], {"x": 1}):
            with self.subTest(body=body):
                self.assertEqual((await self.view.post(self.request(admin, body)))["status"], 400)
        self.assertEqual((await self.view.post(self.request(admin, {"settings": {"threshold": 0.4}})))["status"], 503)

    def test_panel_is_wired(self):
        init = (ROOT / "custom_components/declan_two/__init__.py").read_text()
        self.assertIn("DeclanSpeakerSettingsView()", init)
        js = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()
        for needle in ("declan_two/speaker-settings", "declan_two/history?quality=1", "loadUnderstanding()",
                       "saveSpeakerSettings()", "speaker-settings-form", "understanding-headline"):
            self.assertIn(needle, js)
        self.assertIn('request.query.get("quality") == "1"',
                      (ROOT / "custom_components/declan_two/history_view.py").read_text())


if __name__ == "__main__":
    unittest.main()
