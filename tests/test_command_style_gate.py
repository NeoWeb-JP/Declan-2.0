"""#373 question-first / "my bru" command style gate (D6 defaults: off, silent)."""
import importlib.util
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from declan.http import settings_read_routes
from declan.turn import command_style, turn_preflight
from declan.turn.intent_preprocessing import preprocess_speech
from declan.voice import settings_voice_post

ROOT = Path(__file__).resolve().parents[1]


class RejectionTests(unittest.TestCase):
    def reject(self, phrase, mode="question", **kwargs):
        return command_style.rejection(phrase, mode=mode, source=kwargs.pop("source", "assist"), **kwargs)

    def test_any_mode_and_non_satellite_sources_never_gate(self):
        for phrase in ("turn on the office light", "play country music everywhere"):
            self.assertIsNone(self.reject(phrase, mode="any"))
        for source in ("browser_keyboard", "browser_voice", "ha_sentence", None):
            self.assertIsNone(self.reject("turn on the office light", source=source))

    def test_question_openers_are_accepted(self):
        for phrase in ("Can you turn on the office light?", "could you play country music everywhere",
                       "would you turn off the kitchen lights", "Will you start movie time",
                       "would you mind turning off the bedroom lights", "do you mind dimming the lounge",
                       "please could you turn on the office light", "can you, please, turn on the office light",
                       "Declan, can you turn on the light", "howzit declan could you play jazz",
                       "can you turn on the office light and play country music everywhere"):
            with self.subTest(phrase=phrase):
                self.assertIsNone(self.reject(phrase))

    def test_imperatives_and_late_questions_are_rejected(self):
        for phrase in ("turn on the office light.", "Play country music everywhere",
                       "Declan, turn on the office light", "turn on the office light, can you?",
                       "please turn on the office light", "can you", "may you turn on the light",
                       "turn on the office light my bru"):
            with self.subTest(phrase=phrase):
                self.assertEqual(self.reject(phrase), "not_a_question")

    def test_control_words_questions_and_replies_always_pass(self):
        for phrase in ("stop", "Cancel.", "never mind", "stop routine", "yes", "no", "yes please",
                       "what time is it", "who's home", "How warm is the lounge?", "is the garage open"):
            with self.subTest(phrase=phrase):
                self.assertIsNone(self.reject(phrase))
        self.assertIsNone(self.reject("turn on the office light", awaiting_reply=True))

    def test_my_bru_and_either_modes(self):
        self.assertIsNone(self.reject("turn on the office light my bru", mode="my_bru"))
        self.assertIsNone(self.reject("turn on the office light, my bru, thanks", mode="my_bru"))
        self.assertEqual(self.reject("can you turn on the office light", mode="my_bru"), "no_my_bru")
        self.assertEqual(self.reject("my bru", mode="my_bru"), "no_my_bru")
        self.assertIsNone(self.reject("can you turn on the office light", mode="either"))
        self.assertIsNone(self.reject("play jazz my bru", mode="either"))
        self.assertEqual(self.reject("play jazz", mode="either"), "no_opener_or_my_bru")

    def test_fillers_and_self_corrections_are_removed_first(self):
        spoken = preprocess_speech("erm, can you turn on the light").commands[0]
        self.assertIsNone(self.reject(spoken))
        spoken = preprocess_speech("can you turn on the kitchen, no I mean turn on the lounge").commands[0]
        self.assertEqual(self.reject(spoken), "not_a_question")  # the preflight also checks the original

    def test_preflight_accepts_a_corrected_question(self):
        handler = SimpleNamespace(sent=[], send_json=Mock(), log_error=Mock())
        self.assertFalse(turn_preflight._ignored_by_command_style(
            handler, {}, message="can you turn on the kitchen, no I mean turn on the lounge",
            session_id="s", source="assist", pending_retry=None, preprocess=preprocess_speech,
            record=Mock(), mode="question"))


class PreflightTests(unittest.TestCase):
    def run_gate(self, message, *, mode, source="assist", pending_retry=None):
        handler = SimpleNamespace(sent=[], log_error=Mock())
        handler.send_json = lambda status, payload: handler.sent.append((status, payload))
        record = Mock()
        ignored = turn_preflight._ignored_by_command_style(
            handler, {"speaker": {"name": "Jaco"}}, message=message, session_id="s1", source=source,
            pending_retry=pending_retry, preprocess=preprocess_speech, record=record, mode=mode)
        return ignored, handler.sent, record

    def test_rejected_turn_is_silent_closed_and_recorded(self):
        ignored, sent, record = self.run_gate("turn on the office light", mode="question")
        self.assertTrue(ignored)
        self.assertEqual(sent, [(200, {"reply": "", "session_id": "s1", "outcome": "ignored",
                                       "ignored_reason": "not_a_question", "continue_conversation": False,
                                       "follow_up_timeout": 0})])
        record.assert_called_once_with("s1", "assist", "turn on the office light", "", "ignored",
                                       speaker={"name": "Jaco"})

    def test_accepted_and_off_turns_continue(self):
        for message, mode, kwargs in (("can you turn on the office light", "question", {}),
                                      ("turn on the office light", "any", {}),
                                      ("turn on the office light", "question", {"source": "browser_keyboard"}),
                                      ("turn on the office light", "question", {"pending_retry": {"text": "x"}})):
            with self.subTest(message=message, mode=mode, **kwargs):
                ignored, sent, record = self.run_gate(message, mode=mode, **kwargs)
                self.assertFalse(ignored)
                self.assertEqual(sent, [])
                record.assert_not_called()

    def test_gate_runs_after_cancel_and_confirmation_in_preflight(self):
        source = (ROOT / "declan/turn/turn_preflight.py").read_text()
        body = source.split("def resolve(", 1)[1]
        self.assertLess(body.index("cancel_phrases"), body.index("_ignored_by_command_style("))
        self.assertLess(body.index("confirmation_reply is not None"), body.index("_ignored_by_command_style("))


class SettingsTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.object(command_style, "PATH", Path(folder) / "command-style.json"))
        self.enterContext(patch.dict(os.environ, {}, clear=True))

    def test_default_environment_saved(self):
        self.assertEqual(command_style.listing(), {"style": "any", "source": "default"})
        with patch.dict(os.environ, {"DECLAN_COMMAND_STYLE": " Question "}):
            self.assertEqual(command_style.listing(), {"style": "question", "source": "environment"})
            self.assertEqual(command_style.save({"style": "either"}), {"style": "either", "source": "saved"})
        for payload in (None, {}, {"style": "loud"}, {"style": "any", "x": 1}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                command_style.save(payload)
        command_style.PATH.write_text(json.dumps({"style": "nope"}))
        self.assertEqual(command_style.style(), "any")

    def test_routes_and_gates(self):
        handler = SimpleNamespace(path="/api/settings/command-style", sent=[])
        handler.send_json = lambda status, payload: handler.sent.append((status, payload))
        self.assertTrue(settings_read_routes.handles(handler.path))
        settings_read_routes.dispatch(handler, voicepipeline=None, voice_profiles=None, diagnostics=None,
                                      history=None, ai_budget=None, ai_settings=None, ai_credentials=None,
                                      spotify_playlists=None)
        self.assertEqual(handler.sent[-1], (200, {"style": "any", "source": "default"}))
        names = ("spotify_save", "ai_replace_key", "ai_save", "ai_configured", "music", "spotify_playlists",
                 "playlist_handler", "opener_factory", "voice_manage", "pipeline_error", "profiles_manage",
                 "preview", "apply")
        for body, status in (({"settings": {"style": "question"}}, 200), ({"settings": {"style": "x"}}, 400), ({}, 400)):
            settings_voice_post.dispatch(handler, body, **dict.fromkeys(names))
            self.assertEqual(handler.sent[-1][0], status)
        self.assertEqual(command_style.style(), "question")
        for module in ("get_access_gate_http", "post_route_gate_http", "post_origin_auth_http"):
            self.assertIn('"/api/settings/command-style"', (ROOT / "declan/http" / f"{module}.py").read_text())


class ViewAndPanelTests(unittest.IsolatedAsyncioTestCase):
    async def test_view_validates_and_panel_is_wired(self):
        web = SimpleNamespace(json_response=lambda payload, status=200, headers=None: {"payload": payload, "status": status})
        aiohttp = SimpleNamespace(web=web, ClientTimeout=lambda total: total, ClientError=OSError)
        with patch.dict("sys.modules", {
            "aiohttp": aiohttp, "homeassistant": SimpleNamespace(), "homeassistant.components": SimpleNamespace(),
            "homeassistant.components.http": SimpleNamespace(HomeAssistantView=object),
            "homeassistant.helpers": SimpleNamespace(),
            "homeassistant.helpers.aiohttp_client": SimpleNamespace(async_get_clientsession=lambda hass: None),
        }):
            spec = importlib.util.spec_from_file_location(
                "command_style_view_fixture", ROOT / "custom_components/declan_two/command_style_view.py")
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        view = module.DeclanCommandStyleView()

        def request(user, body):
            class Request(dict):
                app = {"hass": SimpleNamespace(config_entries=SimpleNamespace(async_entries=lambda domain: []))}
                content_length = 30
                content_type = "application/json"

                async def json(self):
                    return body
            return Request(hass_user=user)
        admin = SimpleNamespace(is_admin=True)
        self.assertEqual((await view.get(request(SimpleNamespace(is_admin=False), None)))["status"], 403)
        for body in ({"settings": {"style": "loud"}}, [1], {"x": 1}):
            self.assertEqual((await view.post(request(admin, body)))["status"], 400)
        self.assertEqual((await view.post(request(admin, {"settings": {"style": "question"}})))["status"], 503)
        js = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()
        for needle in ("declan_two/command-style", "loadCommandStyle()", "saveCommandStyle()", 'class="command-style-form"'):
            self.assertIn(needle, js)
        self.assertIn("DeclanCommandStyleView()", (ROOT / "custom_components/declan_two/__init__.py").read_text())


if __name__ == "__main__":
    unittest.main()
