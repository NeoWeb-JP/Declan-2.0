"""Regression checks for Home Assistant speech transport extraction."""
import unittest
from unittest.mock import patch

import server
from declan.ha import ha_speech_transport as transport


class SpeechTransportExtractionTests(unittest.TestCase):
    def test_connection_wrapper_keeps_patch_points(self):
        with patch.object(transport, "ha_device_connection", return_value="connected") as extracted:
            self.assertEqual(server.ha_device_connection(), "connected")
        kwargs = extracted.call_args.kwargs
        self.assertIs(kwargs["environ"], server.os.environ)
        self.assertIs(kwargs["redirect_handler"], server.NoRedirect)
        self.assertIs(kwargs["proxy_handler"], server.ProxyHandler)
        self.assertIs(kwargs["opener_factory"], server.build_opener)

    def test_voice_wrapper_keeps_patch_points(self):
        with patch.object(transport, "render_web_voice", return_value=b"audio") as extracted:
            self.assertEqual(server.render_web_voice("hello"), b"audio")
        kwargs = extracted.call_args.kwargs
        self.assertIs(kwargs["connect"], server.ha_device_connection)
        self.assertIs(kwargs["config"], server.configuration)
        self.assertIs(kwargs["request_factory"], server.Request)

    def test_missing_ha_connection_returns_none(self):
        self.assertIsNone(transport.render_web_voice(
            "hello", connect=lambda: None, config={}, request_factory=server.Request,
        ))

    def test_invalid_tts_entity_returns_none_without_http(self):
        self.assertIsNone(transport.render_web_voice(
            "hello", connect=lambda: ("http://ha", {}, object()),
            config={"DECLAN_WEB_TTS_ENTITY": "invalid"},
            request_factory=server.Request,
        ))

    def test_invalid_connection_configuration(self):
        self.assertIsNone(transport.ha_device_connection(
            environ={"DECLAN_HA_URL": "http://ha", "DECLAN_HA_TOKEN": ""},
            redirect_handler=server.NoRedirect, proxy_handler=server.ProxyHandler,
            opener_factory=server.build_opener,
        ))


if __name__ == "__main__":
    unittest.main()
