"""Regression tests for independent sensitive write gate ownership."""

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from declan.ai import ai_credentials
from declan.voice import voicepipeline
from sensitive_write_state import SensitiveWriteState


class SensitiveWriteStateTests(unittest.TestCase):
    def test_voice_and_credential_locks_are_independent(self):
        state = SensitiveWriteState()
        self.assertTrue(state.voice_reviews.acquire(blocking=False))
        try:
            self.assertFalse(state.voice_reviews.acquire(blocking=False))
            self.assertTrue(state.ai_credentials.acquire(blocking=False))
            state.ai_credentials.release()
        finally:
            state.voice_reviews.release()

    def test_instances_are_isolated(self):
        first, second = SensitiveWriteState(), SensitiveWriteState()
        first.voice_reviews.acquire()
        try:
            self.assertTrue(second.voice_reviews.acquire(blocking=False))
            second.voice_reviews.release()
        finally:
            first.voice_reviews.release()

    def test_credential_read_waits_for_in_process_writer_and_keeps_permissions(self):
        state = SensitiveWriteState()
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(ai_credentials, "PATH", Path(folder) / "key"), \
             patch.object(ai_credentials, "DEFAULT_SENSITIVE_WRITE_STATE", state):
            key = "sk-" + "a" * 24
            ai_credentials.replace_key(key)
            started = threading.Event()
            finished = threading.Event()
            values = []

            def read():
                started.set()
                values.append(ai_credentials.get_key())
                finished.set()

            state.ai_credentials.acquire()
            try:
                thread = threading.Thread(target=read)
                thread.start()
                self.assertTrue(started.wait(5))
                self.assertFalse(finished.wait(0.05))
            finally:
                state.ai_credentials.release()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(values, [key])

    def test_voice_write_gate_released_after_upstream_failure(self):
        state = SensitiveWriteState()
        body = {"operation": "delete_speaker", "speaker_id": "speaker-test",
                "confirm": True}
        calls = []
        def request(method, path, *args, **kwargs):
            calls.append((method, path))
            if method == "GET":
                return [{"id": "speaker-test", "name": "Test"}]
            raise voicepipeline.PipelineError("Unverified upstream result")
        with patch.object(voicepipeline, "DEFAULT_SENSITIVE_WRITE_STATE", state), \
             patch.object(voicepipeline, "request", side_effect=request):
            with self.assertRaises(voicepipeline.PipelineError):
                voicepipeline.manage(body)
            self.assertTrue(state.voice_reviews.acquire(blocking=False))
            state.voice_reviews.release()
        self.assertEqual(calls, [
            ("GET", "/api/v1/speakers"),
            ("DELETE", "/api/v1/speakers/speaker-test"),
        ])


if __name__ == "__main__":
    unittest.main()
