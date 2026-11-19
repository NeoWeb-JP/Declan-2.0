"""HTTP handler extraction preserves routing, settings and transport seams."""
import unittest
from unittest.mock import Mock

import http_handler_adapters as adapters


class HTTPHandlerAdapterTests(unittest.TestCase):
    def setUp(self):
        self.handler = Mock()
        self.r = Mock()
        self.r.os.environ = {"DECLAN_ASSIST_TOKEN": "assist", "DECLAN_HA_TOKEN": "ha"}
        self.r.configuration.get.return_value = "pipeline"
        self.r.__file__ = "/tmp/declan/server.py"
        self.r.Path = __import__("pathlib").Path

    def test_body_and_json_preserve_transport(self):
        adapters.send_body(self.handler, 201, b"hello", "text/plain", r=self.r)
        self.r.http_response_transport.send_body.assert_called_once_with(
            self.handler, 201, b"hello", "text/plain", filename=None,
            logger=self.r.DECLAN_EVENT_LOG)
        adapters.send_json(self.handler, 200, {"ok": True}, r=self.r)
        self.r.http_response_transport.send_json.assert_called_once_with(
            self.handler, 200, {"ok": True}, logger=self.r.DECLAN_EVENT_LOG)

    def test_get_preserves_ingress_and_logo_path(self):
        self.handler.has_ingress_access.return_value = True
        adapters.do_GET(self.handler, r=self.r)
        kwargs = self.r.get_request_dispatch.dispatch.call_args.kwargs
        self.assertEqual(kwargs["assist_token"], "assist")
        self.assertTrue(kwargs["ingress"])
        self.assertEqual(kwargs["logo_path"].name, "logo.png")

    def test_settings_use_server_hooks(self):
        adapters.spotify_settings(self.handler, {"enabled": True}, r=self.r)
        self.r.media_settings_routes.spotify_settings.assert_called_once_with(
            self.handler, {"enabled": True}, music=self.r.music)
        adapters.approved_player_settings(self.handler, r=self.r)
        kwargs = self.r.media_settings_routes.approved_player_settings.call_args.kwargs
        self.assertIs(kwargs["ha_device_connection"], self.r.ha_device_connection)
        self.assertIs(kwargs["approved_media_players"], self.r.approved_media_players)

    def test_transcription_preserves_pipeline_and_token(self):
        adapters.transcribe_browser_audio(self.handler, r=self.r)
        kwargs = self.r.speech_http_routes.transcribe_browser_audio.call_args.kwargs
        self.assertEqual(kwargs["token"], "ha")
        self.assertEqual(kwargs["pipeline"], "pipeline")
        self.assertIs(kwargs["transcribe"], self.r.traced_transcribe_result)


if __name__ == "__main__":
    unittest.main()
