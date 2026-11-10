import json
from unittest import TestCase
from unittest.mock import Mock

from web_stt import AssistSpeechError, run_stt


class WebSpeechTests(TestCase):
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
