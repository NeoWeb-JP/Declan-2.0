import json
from unittest import TestCase
from unittest.mock import Mock, patch
from types import SimpleNamespace

from web_stt import AssistSpeechError, TranscriptionResult, TranscriptionStatus, run_stt, run_stt_result
import web_stt


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
