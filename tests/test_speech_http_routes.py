"""Regression coverage for extracted browser speech HTTP adapters."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

import speech_http_routes as routes


class SpeechHttpRoutesTests(TestCase):
    def setUp(self):
        self.handler = Mock()
        self.handler.headers.get_content_type.return_value = "application/octet-stream"
        self.handler.headers.get.return_value = "4"
        self.handler.rfile.read.return_value = b"1234"
        self.web_stt = Mock()
        self.web_stt.MAX_AUDIO_BYTES = 640000
        self.web_stt.AssistSpeechError = type("AssistSpeechError", (Exception,), {"code": "failed"})
        self.connection = Mock(return_value=("http://ha",))
        self.transcribe = Mock(return_value=SimpleNamespace(text="Hello"))
        self.logger = Mock()

    def stt(self):
        routes.transcribe_browser_audio(
            self.handler, web_stt=self.web_stt,
            connection_factory=self.connection, transcribe=self.transcribe,
            token="secret", pipeline="pipeline", logger=self.logger,
        )

    def test_transcription_success(self):
        self.stt()
        self.transcribe.assert_called_once_with(
            "http://ha", "secret", b"1234", pipeline="pipeline",
        )
        self.handler.send_json.assert_called_once_with(200, {"text": "Hello"})

    def test_rejects_wrong_content_type(self):
        self.handler.headers.get_content_type.return_value = "application/json"
        self.stt()
        self.handler.send_json.assert_called_once_with(
            415, {"error": "Expected microphone audio."},
        )

    def test_rejects_odd_audio_size(self):
        self.handler.headers.get.return_value = "3"
        self.stt()
        self.handler.send_json.assert_called_once_with(
            400, {"error": "Record up to 20 seconds of microphone audio."},
        )

    def test_rejects_truncated_recording(self):
        self.handler.rfile.read.return_value = b"12"
        self.stt()
        self.handler.send_json.assert_called_once_with(
            400, {"error": "The microphone recording was incomplete."},
        )

    def test_home_assistant_unavailable(self):
        self.connection.return_value = None
        self.stt()
        self.handler.send_json.assert_called_once_with(
            503, {"error": "Home Assistant isn't configured."},
        )

    def test_transcription_failure(self):
        self.transcribe.side_effect = self.web_stt.AssistSpeechError("bad")
        self.stt()
        self.handler.send_json.assert_called_once()
        self.assertEqual(self.handler.send_json.call_args.args[0], 502)

    def test_tts_success(self):
        routes.render_tts(self.handler, "hello", render=lambda _: b"mp3")
        self.handler.send_body.assert_called_once_with(200, b"mp3", "audio/mpeg")

    def test_tts_unavailable(self):
        routes.render_tts(self.handler, "hello", render=lambda _: None)
        self.handler.send_json.assert_called_once_with(
            503, {"error": "Declan's voice is unavailable."},
        )
