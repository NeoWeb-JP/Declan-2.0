"""D4: opt-in, bounded, device-free general chat."""
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import server
from declan.ai import ai_budget, general_chat
from declan.core import history
from declan.core.execution_results import ExecutionResult, Outcome
from declan.turn import turn_response_preparation

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


class EligibilityTests(unittest.TestCase):
    def test_questions_and_chat_requests_are_eligible(self):
        for text in ("What's the capital of Peru?", "who wrote dracula", "how far is the moon",
                     "tell me a joke", "explain how a heat pump works", "any ideas for dinner",
                     "Is it a good day for a walk?", "can you tell me a fun fact"):
            with self.subTest(text=text):
                self.assertTrue(general_chat.eligible(text, source="assist"))

    def test_commands_unknown_phrasing_and_other_sources_are_not(self):
        for text in ("turn on the flux capacitor", "flux the capacitor", "can you turn on the porch light",
                     "could you play jazz", "", "x" * 301, "what time is it"):
            with self.subTest(text=text):
                self.assertFalse(general_chat.eligible(text, source="assist", chat_commands={"what time is it"}))
        self.assertFalse(general_chat.eligible("who wrote dracula", source="routine"))


class AnswerTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)

        @contextmanager
        def database():
            with self.db:
                yield self.db
        self.database = database

    def ask(self, opener, *, enabled=True, budget="1.00", text="who wrote dracula"):
        return general_chat.answer(
            text, source="assist", opener=opener, now=NOW, database=self.database,
            settings_reader=lambda: {"enabled": enabled, "monthly_budget_usd": budget},
            ai_settings_reader=lambda: dict(AI), key_reader=lambda: "sk-test")

    def test_disabled_or_ineligible_makes_no_request(self):
        opener = Opener(completed("x"))
        self.assertIsNone(self.ask(opener, enabled=False))
        self.assertIsNone(self.ask(opener, text="turn on the hall light"))
        self.assertEqual(opener.requests, [])

    def test_answers_without_devices_and_settles_spend(self):
        opener = Opener(completed("  Bram   Stoker, in 1897.  "))
        self.assertEqual(self.ask(opener), "Bram Stoker, in 1897.")
        body = opener.requests[0]
        self.assertEqual(set(body) - {"reasoning"}, {"model", "instructions", "input", "max_output_tokens", "store"})
        self.assertNotIn("tools", body)
        self.assertFalse(body["store"])
        self.assertIn("cannot see or control any devices", body["instructions"])
        spent = general_chat.month_spent(self.db, NOW)
        self.assertGreater(spent, 0)
        self.assertEqual(ai_budget.monthly_reserved(self.db, now=NOW), spent)

    def test_chat_slice_and_main_budget_are_enforced(self):
        opener = Opener(completed("x"))
        self.assertIsNone(self.ask(opener, budget="0.04"))  # below one request ceiling
        self.assertEqual(opener.requests, [])
        with self.db:
            self.db.execute("CREATE TABLE IF NOT EXISTS ai_budget (month TEXT PRIMARY KEY, reserved INTEGER NOT NULL)")
            self.db.execute("INSERT INTO ai_budget VALUES ('2026-11', 4990000)")
        self.assertIsNone(self.ask(opener))
        self.assertEqual(opener.requests, [])

    def test_rejected_request_costs_nothing_and_unknown_failure_keeps_reservation(self):
        error = HTTPError("https://api.openai.com", 429, "busy", Message(), io.BytesIO(b""))
        self.assertIsNone(self.ask(Opener(error=error)))
        self.assertEqual(ai_budget.monthly_reserved(self.db, now=NOW), 0)
        self.assertIsNone(self.ask(Opener(error=TimeoutError())))
        self.assertEqual(ai_budget.monthly_reserved(self.db, now=NOW), 50000)

    def test_settings_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "chat.json"
            self.assertEqual(general_chat.read(path), {"enabled": False, "monthly_budget_usd": "1.00"})
            self.assertEqual(general_chat.save({"enabled": True, "monthly_budget_usd": "2.50"}, path)["enabled"], True)
            for payload in ({"enabled": "yes", "monthly_budget_usd": "1"}, {"enabled": True},
                            {"enabled": True, "monthly_budget_usd": "abc"}):
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    general_chat.save(payload, path)


class PreparationTests(unittest.TestCase):
    def prepare(self, *, routine_reply=None, fallback=None, chat="Lima."):
        handler = Mock(return_value=chat)
        result = turn_response_preparation.prepare(
            "what's the capital of peru", routine_reply=routine_reply, outcome=None, light_result=None,
            body={}, authorization="", bridge_token="", source="assist", action_results=[],
            exposed_entities=lambda *a: [], dispatch_fallback=lambda *a, **k: fallback,
            fallback_handler=None, guest_mode_reader=lambda: "off", visitors_reader=lambda: False,
            personality_policy=SimpleNamespace(response_guest_mode=lambda guest, visitor: guest),
            chat_commands={}, information_context=None, chat_handler=handler)
        return result, handler

    def test_unanswered_and_empty_plan_turns_get_chat(self):
        from declan.ai.guarded_fallback import EMPTY_PLAN_REPLY
        for fallback in (None, ExecutionResult(EMPTY_PLAN_REPLY, Outcome.UNRESOLVED)):
            with self.subTest(fallback=fallback):
                result, handler = self.prepare(fallback=fallback)
                self.assertEqual((result.reply, result.outcome), ("Lima.", Outcome.CHAT_ANSWER))
                handler.assert_called_once()

    def test_local_replies_and_other_ai_results_are_kept(self):
        result, handler = self.prepare(routine_reply="Done.")
        self.assertEqual(result.reply, "Done.")
        handler.assert_not_called()
        result, handler = self.prepare(fallback=ExecutionResult("Monthly OpenAI budget exhausted", Outcome.UNRESOLVED))
        self.assertEqual(result.reply, "Monthly OpenAI budget exhausted")
        handler.assert_not_called()


class FullTurnTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(history, 'DATABASE', Path(directory) / 'history.db'))
        self.enterContext(patch.object(server, "SESSION_STORE", server.session_store.SessionStore()))
        self.enterContext(patch.object(server, 'read_guest_mode', return_value='off'))
        self.enterContext(patch.object(server, 'read_visitors_present', return_value=False))
        self.enterContext(patch.object(server, 'guarded_openai_fallback_result', return_value=None))
        self.enterContext(patch.object(server, 'select_routine_turn_result', return_value=None))
        self.enterContext(patch.object(server, 'handle_light_request_result', return_value=None))
        self.enterContext(patch.object(server.CAPTURE_ARBITER, 'claim', return_value=True))
        self.enterContext(patch.dict(server.os.environ, {'DECLAN_ASSIST_TOKEN': 'test'}))

    def ask(self, message):
        handler = object.__new__(server.Handler)
        handler.path = '/api/assist'
        body = json.dumps({"message": message, "device_id": "kitchen"}).encode()
        handler.rfile = io.BytesIO(body)
        handler.headers = Message()
        for key, value in {'Content-Type': 'application/json', 'Content-Length': str(len(body)),
                           'Authorization': 'Bearer test'}.items():
            handler.headers[key] = value
        setattr(handler, "server", SimpleNamespace(bad_tokens=SimpleNamespace(check=lambda *args: 0)))
        handler.client_address = ('127.0.0.1', 1)
        setattr(handler, 'has_ingress_access', lambda: True)
        setattr(handler, 'send_json', Mock())
        setattr(handler, 'log_error', Mock())
        handler.handle_post()
        return cast(Mock, handler.send_json).call_args.args

    def test_chat_answer_is_spoken_recorded_and_closes_the_turn(self):
        with patch.object(general_chat, "answer", return_value="Lima, sir.") as answer:
            status, result = self.ask("what's the capital of peru")
        self.assertEqual(status, 200)
        self.assertIn("Lima, sir.", result["reply"])
        self.assertFalse(result["continue_conversation"])
        self.assertEqual(answer.call_args.kwargs["source"], "assist")
        with closing(sqlite3.connect(history.DATABASE)) as db:
            self.assertEqual(db.execute("SELECT outcome FROM turns").fetchall(), [("chat_answer",)])

    def test_without_chat_the_rephrase_prompt_is_unchanged(self):
        with patch.object(general_chat, "answer", return_value=None):
            _, result = self.ask("flux the capacitor")
        self.assertEqual(result["reply"], server.UNMATCHED_REPLY)
        self.assertTrue(result["continue_conversation"])


if __name__ == "__main__":
    unittest.main()


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
            self.assertEqual(handler.sent[-1], (200, {"settings": {"enabled": False, "monthly_budget_usd": "1.00"},
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
