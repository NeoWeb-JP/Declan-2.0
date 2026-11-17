"""Verify persisted browser TTS entity overrides fail closed."""
import unittest
from unittest.mock import patch

import server


class WebTTSEntityConfigurationTests(unittest.TestCase):
    def test_invalid_tts_entity_does_not_open_home_assistant_request(self):
        for entity in ("sensor.speaker", "tts.", "tts.Engine", "tts.engine/../other",
                       "tts.engine?x=1", "tts.engine#fragment"):
            with self.subTest(entity=entity), patch.object(
                    server.configuration, "get", return_value=entity), patch.object(
                    server, "ha_device_connection", return_value=(
                        "https://ha.example", {}, object())), patch.object(
                    server, "Request") as request:
                self.assertIsNone(server.render_web_voice("Hello"))
                request.assert_not_called()

    def test_unconfigured_home_assistant_does_not_request_tts(self):
        with patch.object(server.configuration, "get", return_value="tts.example"), patch.object(
                server, "ha_device_connection", return_value=None), patch.object(
                server, "Request") as request:
            self.assertIsNone(server.render_web_voice("Hello"))
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
