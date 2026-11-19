"""Typed connection health keeps execution outcomes and credentials separate."""
from http_test_doubles import HTTPResponse
from email.message import Message
import io
import json
import sqlite3
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from home_assistant_results import HomeAssistantStatus, HomeAssistantStatusResult
import server


class HomeAssistantStatusResultTests(unittest.TestCase):
    def probe(self, *, status=200, payload=None, error=None):
        opener = Mock()
        response = HTTPResponse(json.dumps({"message": "API running."} if payload is None else payload).encode())
        response.status = status
        opener.open.return_value = response
        if error is not None:
            opener.open.side_effect = error
        with patch.dict(server.os.environ, {"DECLAN_HA_URL": "https://ha.local", "DECLAN_HA_TOKEN": "secret-token"}), \
             patch.object(server, "build_opener", return_value=opener), \
             patch.object(server, "home_assistant_status", side_effect=AssertionError("legacy roundtrip")):
            result = server.home_assistant_status_result()
        return result, opener

    def test_connected_requires_exact_health_response_and_does_not_retain_credentials(self):
        result, opener = self.probe()
        self.assertIs(result.status, HomeAssistantStatus.CONNECTED)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://ha.local/api/")
        self.assertEqual(opener.open.call_args.kwargs, {"timeout": 3})
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-token")
        self.assertNotIn("secret-token", str(result))
        self.assertNotIn("ha.local", str(result))
        with self.assertRaises(AttributeError):
            setattr(result, "status", HomeAssistantStatus.DISCONNECTED)
        for status, payload in ((200, {}), (204, {"message": "API running."}),
                (200, {"message": "API running.", "extra": True}), (200, [])):
            self.assertIs(self.probe(status=status, payload=payload)[0].status, HomeAssistantStatus.DISCONNECTED)

    def test_authentication_and_transport_failures_have_distinct_typed_statuses(self):
        for status, expected in ((401, HomeAssistantStatus.AUTHENTICATION_FAILED),
                (403, HomeAssistantStatus.AUTHENTICATION_FAILED), (500, HomeAssistantStatus.DISCONNECTED),
                (302, HomeAssistantStatus.DISCONNECTED)):
            with self.subTest(status=status):
                body = io.BytesIO(b"secret error body")
                result, _ = self.probe(error=HTTPError("https://ha.local", status, "secret error", Message(), body))
                self.assertIs(result.status, expected)
                self.assertTrue(body.closed)
                self.assertNotIn("secret", str(result))
        for error in (TimeoutError("secret timeout"), ValueError("secret invalid JSON")):
            self.assertIs(self.probe(error=error)[0].status, HomeAssistantStatus.DISCONNECTED)

    def test_missing_credentials_preserve_recent_assist_fallback(self):
        for recent, expected in ((True, HomeAssistantStatus.ASSIST_RECENT), (False, HomeAssistantStatus.NOT_CONFIGURED)):
            with patch.dict(server.os.environ, {"DECLAN_HA_URL": "", "DECLAN_HA_TOKEN": ""}), \
                 patch.object(server.history, "has_recent_assist", return_value=recent), \
                 patch.object(server, "build_opener") as build:
                self.assertIs(server.home_assistant_status_result().status, expected)
            build.assert_not_called()
        with patch.dict(server.os.environ, {"DECLAN_HA_URL": "", "DECLAN_HA_TOKEN": ""}), \
             patch.object(server.history, "has_recent_assist", side_effect=sqlite3.Error("secret")):
            self.assertIs(server.home_assistant_status_result().status, HomeAssistantStatus.NOT_CONFIGURED)

    def test_invalid_urls_do_not_probe_or_claim_connection(self):
        for url in ("ftp://ha.local", "https://user:password@ha.local", "https://ha.local?token=secret", "https://ha.local#secret", "https://"):
            with self.subTest(url=url), patch.dict(server.os.environ, {"DECLAN_HA_URL": url, "DECLAN_HA_TOKEN": "secret"}), \
                 patch.object(server, "build_opener") as build:
                self.assertIs(server.home_assistant_status_result().status, HomeAssistantStatus.NOT_CONFIGURED)
            build.assert_not_called()

    def test_public_status_api_preserves_plain_strings(self):
        for status in HomeAssistantStatus:
            with patch.object(server, "home_assistant_status_result", return_value=HomeAssistantStatusResult(status)):
                value = server.home_assistant_status()
            self.assertEqual(value, status.value)
            self.assertIs(type(value), str)
