"""Server-level wiring for HTTP handler methods, startup and typed routine helpers."""
from unittest.mock import patch
import unittest

import server


class ServerHandlerWiringTests(unittest.TestCase):
    def handler(self):
        handler = server.Handler.__new__(server.Handler)
        return handler

    def test_body_and_json_preserve_transport(self):
        handler = self.handler()
        with patch.object(server.http_response_transport, "send_body") as body:
            handler.send_body(201, b"hello", "text/plain")
        body.assert_called_once_with(handler, 201, b"hello", "text/plain", filename=None,
                                     logger=server.DECLAN_EVENT_LOG)
        with patch.object(server.http_response_transport, "send_json") as send:
            handler.send_json(200, {"ok": True})
        send.assert_called_once_with(handler, 200, {"ok": True}, logger=server.DECLAN_EVENT_LOG)

    def test_get_preserves_ingress_logo_and_assist_token(self):
        handler = self.handler()
        with patch.dict(server.os.environ, {"DECLAN_ASSIST_TOKEN": "assist"}), \
             patch.object(server.Handler, "has_ingress_access", return_value=True), \
             patch.object(server.get_request_dispatch, "dispatch") as dispatch:
            handler.do_GET()
        kwargs = dispatch.call_args.kwargs
        self.assertEqual(kwargs["assist_token"], "assist")
        self.assertTrue(kwargs["ingress"])
        self.assertEqual(kwargs["logo_path"].name, "logo.png")

    def test_settings_use_server_hooks(self):
        handler = self.handler()
        with patch.object(server.media_settings_routes, "spotify_settings") as spotify:
            handler.spotify_settings({"enabled": True})
        spotify.assert_called_once_with(handler, {"enabled": True}, music=server.music)
        with patch.object(server.media_settings_routes, "approved_player_settings") as players:
            handler.approved_player_settings()
        kwargs = players.call_args.kwargs
        self.assertIs(kwargs["ha_device_connection"], server.ha_device_connection)
        self.assertIs(kwargs["approved_media_players"], server.approved_media_players)

    def test_transcription_preserves_pipeline_and_token(self):
        handler = self.handler()
        with patch.dict(server.os.environ, {"DECLAN_HA_TOKEN": "ha"}), \
             patch.object(server.configuration, "get", return_value="pipeline"), \
             patch.object(server.speech_http_routes, "transcribe_browser_audio") as route:
            handler.transcribe_browser_audio()
        kwargs = route.call_args.kwargs
        self.assertEqual(kwargs["token"], "ha")
        self.assertEqual(kwargs["pipeline"], "pipeline")
        self.assertIs(kwargs["transcribe"], server.traced_transcribe_result)

    def test_http_headers_are_secured_before_base_finalize(self):
        handler = self.handler()
        calls = []
        with patch.object(server.http_ingress_security, "send_security_headers",
                          side_effect=lambda value: calls.append(("security", value))), \
             patch.object(server.BaseHTTPRequestHandler, "end_headers",
                          side_effect=lambda value: calls.append(("base", value))):
            handler.end_headers()
        self.assertEqual(calls, [("security", handler), ("base", handler)])

    def test_main_preserves_lifecycle_dependencies(self):
        with patch.object(server.server_lifecycle, "main", return_value="started") as lifecycle:
            self.assertEqual(server.main(), "started")
        kwargs = lifecycle.call_args.kwargs
        self.assertIs(kwargs["handler"], server.Handler)
        self.assertIs(kwargs["ha_connect"], server.ha_device_connection)
        self.assertIs(kwargs["music_inventory"], server.read_music_inventory_result)
        self.assertIs(kwargs["logger"], server.DECLAN_EVENT_LOG)

    def test_routine_tracker_and_evidence_use_live_state(self):
        with patch.object(server.ACTIVE_ROUTINE_REGISTRY, "track", return_value="tracked") as track:
            self.assertEqual(server.track_routine("tea", "script.tea"), "tracked")
        track.assert_called_once_with("tea", "script.tea")
        self.assertEqual(server.routine_action_results_typed(None), ())


if __name__ == "__main__":
    unittest.main()
