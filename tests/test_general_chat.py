"""D4: opt-in, bounded, device-free general chat."""
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

from declan.ai import ai_budget, general_chat
from declan.core import history

NOW = datetime(2026, 11, 20, tzinfo=timezone.utc)
AI = {"model": "gpt-5-mini", "model_config": None, "monthly_budget_usd": "5.00", "request_ceiling_usd": "0.05"}


class Opener:
    def __init__(self, payload=None, error=None):
        self.payload, self.error, self.requests = payload, error, []

    def open(self, request, timeout):
        self.requests.append(json.loads(request.data))
        if self.error:
            raise self.error
        body = json.dumps(self.payload).encode()

        @contextmanager
        def response():
            yield io.BytesIO(body)
        return response()


def completed(text, usage=None):
    return {"status": "completed", "usage": usage or {"input_tokens": 300, "output_tokens": 40},
            "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}]}


class CallTests(unittest.TestCase):
    """Shared budgeted model call used by the conversation agent."""
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)

        @contextmanager
        def database():
            with self.db:
                yield self.db
        self.database = database
        self.config = general_chat.model_config(ai_settings_reader=lambda: dict(AI), key_reader=lambda: "sk-test")

    def call(self, opener, *, enabled=True, budget="20.00"):
        body = {"model": "gpt-5-mini", "input": "hi", "instructions": "x", "max_output_tokens": 100, "store": False}
        return general_chat.call(body, config=self.config, settings={"enabled": enabled, "monthly_budget_usd": budget},
                                 opener=opener, database=self.database, now=NOW)

    def test_disabled_makes_no_request(self):
        opener = Opener(completed("x"))
        with self.assertRaises(general_chat.ModelUnavailable):
            self.call(opener, enabled=False)
        self.assertEqual(opener.requests, [])

    def test_reply_and_spend_in_both_ledgers(self):
        self.assertEqual(self.call(Opener(completed("hello"))), "hello")
        spent = general_chat.month_spent(self.db, NOW)
        self.assertGreater(spent, 0)
        self.assertEqual(ai_budget.monthly_reserved(self.db, now=NOW), spent)

    def test_slice_and_main_budget_are_enforced(self):
        opener = Opener(completed("x"))
        with self.assertRaises(general_chat.ModelUnavailable):
            self.call(opener, budget="0.04")
        with self.db:
            self.db.execute("CREATE TABLE IF NOT EXISTS ai_budget (month TEXT PRIMARY KEY, reserved INTEGER NOT NULL)")
            self.db.execute("INSERT INTO ai_budget VALUES ('2026-11', 4990000)")
        with self.assertRaises(general_chat.ModelUnavailable):
            self.call(opener)
        self.assertEqual(opener.requests, [])

    def test_rejected_costs_nothing_unknown_failure_keeps_reservation(self):
        error = HTTPError("https://api.openai.com", 429, "busy", Message(), io.BytesIO(b""))
        with self.assertRaises(general_chat.ModelUnavailable):
            self.call(Opener(error=error))
        self.assertEqual(ai_budget.monthly_reserved(self.db, now=NOW), 0)
        with self.assertRaises(general_chat.ModelUnavailable):
            self.call(Opener(error=TimeoutError()))
        self.assertEqual(ai_budget.monthly_reserved(self.db, now=NOW), 50000)

    def test_missing_key_is_unavailable(self):
        with self.assertRaises(general_chat.ModelUnavailable):
            general_chat.model_config(ai_settings_reader=lambda: dict(AI), key_reader=lambda: "")

    def test_settings_validation_and_default_budget(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "chat.json"
            self.assertEqual(general_chat.read(path), {"enabled": False, "monthly_budget_usd": "20.00"})
            self.assertTrue(general_chat.save({"enabled": True, "monthly_budget_usd": "2.50"}, path)["enabled"])
            for payload in ({"enabled": "yes", "monthly_budget_usd": "1"}, {"enabled": True},
                            {"enabled": True, "monthly_budget_usd": "abc"}):
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    general_chat.save(payload, path)


class SettingsRouteAndPanelTests(unittest.IsolatedAsyncioTestCase):
    async def test_routes_view_and_panel(self):
        import importlib.util
        import os

        from declan.http import settings_read_routes
        from declan.voice import settings_voice_post
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(general_chat, "PATH", Path(folder) / "chat.json"), \
                patch.object(history, "DATABASE", Path(folder) / "history.db"):
            handler = SimpleNamespace(path="/api/settings/chat", sent=[])
            handler.send_json = lambda status, payload: handler.sent.append((status, payload))
            settings_read_routes.dispatch(handler, voicepipeline=None, voice_profiles=None, diagnostics=None,
                                          history=None, ai_budget=None, ai_settings=None, ai_credentials=None,
                                          spotify_playlists=None)
            self.assertEqual(handler.sent[-1], (200, {"settings": {"enabled": False, "monthly_budget_usd": "20.00"},
                                                      "month_spent_micro_usd": 0}))
            names = ("spotify_save", "ai_replace_key", "ai_save", "ai_configured", "music", "spotify_playlists",
                     "playlist_handler", "opener_factory", "voice_manage", "pipeline_error", "profiles_manage",
                     "preview", "apply")
            settings_voice_post.dispatch(handler, {"settings": {"enabled": True, "monthly_budget_usd": "2.00"}},
                                         **dict.fromkeys(names))
            self.assertEqual(handler.sent[-1][1]["settings"]["enabled"], True)
            settings_voice_post.dispatch(handler, {"settings": {"enabled": 1, "monthly_budget_usd": "2"}},
                                         **dict.fromkeys(names))
            self.assertEqual(handler.sent[-1][0], 400)
        for gate in ("get_access_gate_http", "post_route_gate_http", "post_origin_auth_http"):
            self.assertIn('"/api/settings/chat"', (root / "declan/http" / f"{gate}.py").read_text())
        web = SimpleNamespace(json_response=lambda payload, status=200, headers=None: {"payload": payload, "status": status})
        aiohttp = SimpleNamespace(web=web, ClientTimeout=lambda total: total, ClientError=OSError)
        with patch.dict("sys.modules", {
            "aiohttp": aiohttp, "homeassistant": SimpleNamespace(), "homeassistant.components": SimpleNamespace(),
            "homeassistant.components.http": SimpleNamespace(HomeAssistantView=object),
            "homeassistant.helpers": SimpleNamespace(),
            "homeassistant.helpers.aiohttp_client": SimpleNamespace(async_get_clientsession=lambda hass: None),
        }):
            spec = importlib.util.spec_from_file_location(
                "chat_settings_view_fixture", root / "custom_components/declan_two/chat_settings_view.py")
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        view = module.DeclanChatSettingsView()

        def request(user, body):
            class Request(dict):
                app = {"hass": SimpleNamespace(config_entries=SimpleNamespace(async_entries=lambda domain: []))}
                content_length = 60
                content_type = "application/json"

                async def json(self):
                    return body
            return Request(hass_user=user)
        admin = SimpleNamespace(is_admin=True)
        self.assertEqual((await view.get(request(SimpleNamespace(is_admin=False), None)))["status"], 403)
        for body in ({"settings": {"enabled": "1", "monthly_budget_usd": "1"}}, {"settings": {"enabled": True}}, [1]):
            self.assertEqual((await view.post(request(admin, body)))["status"], 400)
        good = {"settings": {"enabled": True, "monthly_budget_usd": "1.50"}}
        self.assertEqual((await view.post(request(admin, good)))["status"], 503)
        js = (root / "custom_components/declan_two/frontend/panel.js").read_text()
        for needle in ("declan_two/chat-settings", "loadChatSettings()", "saveChatSettings()", 'class="chat-settings-form"'):
            self.assertIn(needle, js)
        self.assertIn("DeclanChatSettingsView()", (root / "custom_components/declan_two/__init__.py").read_text())
        self.assertTrue(os.path.exists(root / "custom_components/declan_two/chat_settings_view.py"))
