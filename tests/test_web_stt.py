import json
from typing import Any
from unittest import TestCase
from unittest.mock import Mock, patch
from types import SimpleNamespace

from declan.voice.web_stt import AssistSpeechError, TranscriptionResult, TranscriptionStatus, run_stt, run_stt_result
from declan.voice import web_stt


class WebSpeechTests(TestCase):
    @staticmethod
    def socket_for(event):
        socket = Mock()
        socket.recv.side_effect = map(json.dumps, [{"type": "auth_required"}, {"type": "auth_ok"},
                                                 {"id": 1, "event": event}])
        return socket

    def test_typed_pipeline_distinguishes_text_and_empty_completion(self):
        for value, expected in ((" Hello ", "Hello"), ("  ", ""), (None, ""), (123, "")):
            event = {"type": "stt-end", "data": {"stt_output": {"text": value}}}
            result = run_stt_result(self.socket_for(event), "test-token", b"\0\1", None)
            self.assertEqual(result.text, expected)
            self.assertIs(result.status, TranscriptionStatus.TRANSCRIBED if expected else TranscriptionStatus.NO_TEXT)
            legacy = run_stt(self.socket_for(event), "test-token", b"\0\1", None)
            self.assertEqual(legacy, expected)
            self.assertIs(type(legacy), str)
            with self.assertRaises(AttributeError):
                setattr(result, "text", "changed")
        self.assertIs(run_stt_result(self.socket_for({"type": "run-end"}), "token", b"\0\1", None).status,
                      TranscriptionStatus.NO_TEXT)
        with self.assertRaises(ValueError):
            TranscriptionResult(TranscriptionStatus.TRANSCRIBED, "")
        with self.assertRaises(ValueError):
            TranscriptionResult(TranscriptionStatus.NO_TEXT, "Hello")

    def test_transport_consumes_typed_pipeline_and_preserves_cleanup_and_legacy_api(self):
        socket = Mock()
        websocket = SimpleNamespace(create_connection=Mock(return_value=socket),
                                    WebSocketException=type("WebSocketFailure", (Exception,), {}))
        expected = TranscriptionResult.from_text("Hello")
        with patch.dict("sys.modules", {"websocket": websocket}), \
             patch.object(web_stt, "run_stt", side_effect=AssertionError("legacy pipeline")), \
             patch.object(web_stt, "run_stt_result", return_value=expected) as pipeline:
            self.assertIs(web_stt.transcribe_result("https://ha.local", "token", b"\0\1", pipeline="selected"), expected)
            self.assertEqual(web_stt.transcribe("https://ha.local", "token", b"\0\1", pipeline="selected"), "Hello")
        pipeline.assert_called_with(socket, "token", b"\0\1", "selected")
        self.assertEqual(socket.close.call_count, 2)
        socket.close.assert_called_with(timeout=0)
        for error in (AssistSpeechError("stt-provider-missing"), TimeoutError()):
            socket.reset_mock()
            with patch.dict("sys.modules", {"websocket": websocket}), \
                 patch.object(web_stt, "run_stt_result", side_effect=error), self.assertRaises(type(error)):
                web_stt.transcribe_result("https://ha.local", "token", b"\0\1")
            socket.close.assert_called_once_with(timeout=0)

    def test_websocket_endpoint_normalises_trailing_slash_and_proxy_prefix(self):
        websocket = SimpleNamespace(create_connection=Mock(return_value=Mock()),
                                    WebSocketException=type("WebSocketFailure", (Exception,), {}))
        cases = {
            "https://ha.local": "wss://ha.local/api/websocket",
            "https://ha.local/": "wss://ha.local/api/websocket",
            "http://ha.local:8123/": "ws://ha.local:8123/api/websocket",
            "https://ha.local/base": "wss://ha.local/base/api/websocket",
            "https://ha.local/base/": "wss://ha.local/base/api/websocket",
        }
        for url, endpoint in cases.items():
            with self.subTest(url=url), patch.dict("sys.modules", {"websocket": websocket}), \
                 patch.object(web_stt, "run_stt_result", return_value=TranscriptionResult.from_text("Hi")):
                web_stt.transcribe_result(url, "token", b"\0\1")
                self.assertEqual(websocket.create_connection.call_args.args[0], endpoint)

    def test_reports_home_assistant_pipeline_error_code(self):
        socket = Mock()
        socket.recv.side_effect = map(json.dumps, [
            {"type": "auth_required"}, {"type": "auth_ok"},
            {"id": 1, "type": "event", "event": {"type": "error", "data": {"code": "stt-provider-missing"}}},
        ])
        with self.assertRaisesRegex(AssistSpeechError, "stt-provider-missing"):
            run_stt(socket, "test-token", b"\0\1", None)

    def test_assist_run_uses_selected_pipeline_and_sends_pcm(self):
        socket = Mock()
        socket.recv.side_effect = map(json.dumps, [
            {"type": "auth_required"},
            {"type": "auth_ok"},
            {"id": 1, "type": "result", "success": True},
            {"id": 1, "event": {"type": "run-start", "data": {"runner_data": {"stt_binary_handler_id": 7}}}},
            {"id": 1, "event": {"type": "stt-start"}},
            {"id": 1, "event": {"type": "stt-end", "data": {"stt_output": {"text": " Hello "}}}},
        ])
        self.assertEqual(run_stt(socket, "test-token", b"\0\1", "selected"), "Hello")
        command = json.loads(socket.send.call_args.args[0])
        self.assertEqual(command["pipeline"], "selected")
        self.assertEqual(command["end_stage"], "stt")
        self.assertEqual(command["input"]["sample_rate"], 16000)
        self.assertEqual([call.args[0] for call in socket.send_binary.call_args_list], [b"\7\0\1", b"\7"])


class WebSpeechRobustnessTests(TestCase):
    """#848 P1: deadline, unrelated messages, malformed shapes and repeats."""

    @staticmethod
    def socket_with(*messages):
        socket = Mock()
        socket.recv.side_effect = [m if isinstance(m, (str, bytes)) else json.dumps(m) for m in
                                   ({"type": "auth_required"}, {"type": "auth_ok"}, *messages)]
        return socket

    def test_deadline_bounds_every_read_and_is_never_extended_by_unrelated_messages(self):
        clock = iter([0, 1, 2, 10, 20, 24.5, 25.1])
        socket = self.socket_with(*({"id": 99, "type": "event", "event": {"type": "stt-end"}},) * 5)
        with patch.object(web_stt, "monotonic", side_effect=lambda: next(clock)), \
                self.assertRaisesRegex(TimeoutError, "timed out"):
            run_stt_result(socket, "token", b"\0\1", None)
        timeouts = [call.args[0] for call in socket.settimeout.call_args_list]
        self.assertEqual(timeouts, sorted(timeouts, reverse=True))
        self.assertTrue(all(0 < value <= 25 for value in timeouts))
        socket.send_binary.assert_not_called()

    def test_unrelated_ids_are_ignored_and_audio_is_sent_once(self):
        socket = self.socket_with(
            {"id": 2, "type": "event", "event": {"type": "stt-start"}},
            {"id": 1, "type": "result", "success": True},
            {"id": 1, "type": "event", "event": {"type": "run-start",
                                                 "data": {"runner_data": {"stt_binary_handler_id": 3}}}},
            {"id": 1, "type": "event", "event": {"type": "stt-start"}},
            {"id": 1, "type": "event", "event": {"type": "stt-start"}},
            {"id": 1, "type": "event", "event": {"type": "stt-end", "data": {"stt_output": {"text": "Hi"}}}},
        )
        self.assertEqual(run_stt_result(socket, "token", b"\0\1", None).text, "Hi")
        self.assertEqual([c.args[0] for c in socket.send_binary.call_args_list], [b"\3\0\1", b"\3"])

    def test_malformed_messages_are_reported_as_invalid_not_attribute_errors(self):
        start = {"id": 1, "type": "event", "event": {"type": "run-start",
                                                     "data": {"runner_data": {"stt_binary_handler_id": 3}}}}
        cases: dict[str, list[Any]] = {
            "event is a list": [{"id": 1, "type": "event", "event": ["stt-end"]}],
            "data is a string": [{"id": 1, "type": "event", "event": {"type": "stt-end", "data": "x"}}],
            "stt_output is a list": [{"id": 1, "type": "event",
                                      "event": {"type": "stt-end", "data": {"stt_output": ["x"]}}}],
            "runner_data is a list": [{"id": 1, "type": "event",
                                       "event": {"type": "run-start", "data": {"runner_data": [3]}}}],
            "result error is a string": [{"id": 1, "type": "result", "success": False, "error": "boom"}],
            "not JSON": ["<html>proxy error</html>"],
            "handler out of range": [{"id": 1, "type": "event", "event": {
                "type": "run-start", "data": {"runner_data": {"stt_binary_handler_id": 256}}}},
                {"id": 1, "type": "event", "event": {"type": "stt-start"}}],
            "stt-start before run-start": [{"id": 1, "type": "event", "event": {"type": "stt-start"}}],
            "bool handler": [{"id": 1, "type": "event", "event": {
                "type": "run-start", "data": {"runner_data": {"stt_binary_handler_id": True}}}},
                {"id": 1, "type": "event", "event": {"type": "stt-start"}}],
        }
        for name, messages in cases.items():
            with self.subTest(case=name):
                socket = self.socket_with(*messages)
                with self.assertRaises(ValueError) as caught:
                    run_stt_result(socket, "token", b"\0\1", None)
                if name == "result error is a string":
                    self.assertIsInstance(caught.exception, AssistSpeechError)
                    self.assertEqual(getattr(caught.exception, "code", None), "unknown")
                socket.send_binary.assert_not_called()
        # A well-formed run is unaffected by the stricter shape checks.
        socket = self.socket_with(start, {"id": 1, "type": "event", "event": {"type": "stt-start"}},
                                  {"id": 1, "type": "event", "event": {"type": "run-end"}})
        self.assertEqual(run_stt_result(socket, "token", b"\0\1", None).status, TranscriptionStatus.NO_TEXT)

    def test_connection_drop_and_rejected_auth_are_typed(self):
        failure = type("WebSocketFailure", (Exception,), {})
        socket = Mock()
        socket.recv.side_effect = [json.dumps({"type": "auth_required"}), failure("closed")]
        websocket = SimpleNamespace(create_connection=Mock(return_value=socket), WebSocketException=failure)
        with patch.dict("sys.modules", {"websocket": websocket}), self.assertRaises(OSError):
            web_stt.transcribe_result("https://ha.local", "token", b"\0\1")
        socket.close.assert_called_once_with(timeout=0)
        rejected = Mock()
        rejected.recv.side_effect = map(json.dumps, [{"type": "auth_required"}, {"type": "auth_invalid"}])
        with self.assertRaises(AssistSpeechError) as caught:
            run_stt_result(rejected, "token", b"\0\1", None)
        self.assertEqual(caught.exception.code, "auth-rejected")
