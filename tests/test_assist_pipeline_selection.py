"""Verify browser Assist pipeline selection is optional and explicit."""
import json
import unittest
from unittest.mock import Mock

import web_stt


class AssistPipelineSelectionTests(unittest.TestCase):
    @staticmethod
    def capture_messages(pipeline):
        socket = Mock()
        messages = [
            {"type": "auth_required"},
            {"type": "auth_ok"},
            {"id": 1, "event": {"type": "run-end"}},
        ]
        socket.recv.side_effect = [json.dumps(message) for message in messages]
        web_stt.run_stt_result(socket, "test-token", b"\\0\\1", pipeline)
        return [json.loads(call.args[0]) for call in socket.send.call_args_list]

    def test_missing_or_empty_pipeline_uses_home_assistant_default(self):
        for pipeline in (None, ""):
            with self.subTest(pipeline=pipeline):
                sent = self.capture_messages(pipeline)
                self.assertNotIn("pipeline", sent[1])
                self.assertEqual(sent[1]["start_stage"], "stt")
                self.assertEqual(sent[1]["end_stage"], "stt")

    def test_configured_pipeline_is_sent_unchanged(self):
        sent = self.capture_messages("pipeline-id-123")
        self.assertEqual(sent[1]["pipeline"], "pipeline-id-123")
        self.assertEqual(sent[0], {"type": "auth", "access_token": "test-token"})


if __name__ == "__main__":
    unittest.main()
