"""HTTP response transport compatibility and privacy tests."""

import io
import json
import logging
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from declan.http import http_response_transport


class FakeHandler:
    def __init__(self, path="/api/chat", command="POST"):
        self.path = path
        self.command = command
        self.wfile = io.BytesIO()
        self.headers = []
        self.status = None
        self._page_nonce = None

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.headers.append((name, value))

    def end_headers(self):
        pass


class ResponseTransportTests(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger("test.http_response_transport")

    def test_json_response_keeps_wire_contract(self):
        handler = FakeHandler()
        with patch.object(http_response_transport.diagnostics, "ACTIVE", SimpleNamespace(get=lambda: None)):
            http_response_transport.send_json(handler, 200, {"reply": "hello"}, logger=self.logger)
        self.assertEqual(handler.status, 200)
        self.assertEqual(json.loads(handler.wfile.getvalue()), {"reply": "hello"})
        self.assertIn(("Content-Type", "application/json"), handler.headers)
        self.assertIn(("Cache-Control", "no-store"), handler.headers)

    def test_assist_posts_are_logged_and_quiet_reads_are_not(self):
        with self.assertLogs(self.logger, level="INFO") as logs:
            http_response_transport.send_body(
                FakeHandler("/api/assist?debug=1", "POST"), 200, b"{}", "application/json", logger=self.logger)
            http_response_transport.send_body(
                FakeHandler("/api/history", "GET"), 200, b"{}", "application/json", logger=self.logger)
            http_response_transport.send_body(
                FakeHandler("/api/settings/ai", "GET"), 403, b"{}", "application/json", logger=self.logger)
        self.assertEqual([record.getMessage() for record in logs.records],
                         ["HTTP 200 POST /api/assist", "HTTP 403 GET /api/settings/ai"])
        self.assertEqual(logs.records[1].levelname, "WARNING")

    def test_query_parameters_not_logged(self):
        handler = FakeHandler("/api/chat?token=private", command="POST")
        with patch.object(http_response_transport.diagnostics, "ACTIVE", SimpleNamespace(get=lambda: None)):
            with self.assertLogs("test.http_response_transport", level="INFO") as captured:
                http_response_transport.send_body(
                    handler, 400, b"error", "text/plain", logger=self.logger,
                )
        self.assertIn("HTTP 400 POST /api/chat", captured.output[0])
        self.assertNotIn("private", captured.output[0])

    def test_health_response_keeps_pid_header(self):
        handler = FakeHandler("/health", command="GET")
        with patch.object(http_response_transport.diagnostics, "ACTIVE", SimpleNamespace(get=lambda: None)):
            http_response_transport.send_body(
                handler, 200, b"ok", "text/plain", logger=self.logger,
            )
        self.assertTrue(any(name == "X-Declan-Pid" for name, _ in handler.headers))


if __name__ == "__main__":
    unittest.main()
