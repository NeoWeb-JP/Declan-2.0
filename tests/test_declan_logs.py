"""Regression coverage for the bounded native Declan log feed."""
import logging
import unittest
from unittest.mock import patch

import declan_logs


class DeclanLogTests(unittest.TestCase):
    def setUp(self):
        with declan_logs.STATE.lock:
            declan_logs.STATE.entries.clear()
        declan_logs.install()

    def test_captures_only_declan_logs_and_redacts_tokens(self):
        logger = logging.getLogger("spotify_playlists")
        with patch.object(logger, "disabled", False):
            logger.warning("Spotify HTTP 403 Authorization: Bearer abc.secret-token")
        logging.getLogger("unrelated_integration").warning("Unrelated integration warning")
        entries = declan_logs.recent()
        self.assertEqual(len(entries), 1)
        self.assertIn("HTTP 403", entries[0]["message"])
        self.assertNotIn("abc.secret-token", entries[0]["message"])
        self.assertIn("[REDACTED]", entries[0]["message"])

    def test_level_filter_and_bounded_storage(self):
        logger = logging.getLogger("spotify_playlists")
        logger.warning("Warning")
        logger.error("Error")
        self.assertEqual(len(declan_logs.recent("ERROR")), 1)
        self.assertEqual(declan_logs.recent("ERROR")[0]["message"], "Error")
        with self.assertRaises(ValueError):
            declan_logs.recent(limit=1000)

    def test_server_emits_operational_events_without_sensitive_request_data(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        server_source = (root / "server.py").read_text()
        transport_source = (root / "http_response_transport.py").read_text()
        lifecycle_source = (root / "server_lifecycle.py").read_text()
        runtime_source = (root / 'server_runtime_state.py').read_text()
        self.assertIn('server_runtime_state.create_runtime(', server_source)
        self.assertIn('logging_module.getLogger("declan.server")', runtime_source)
        self.assertIn('event_log.setLevel(logging_module.INFO)', runtime_source)
        self.assertIn('Declan backend started and health check passed', lifecycle_source)
        self.assertIn('http_response_transport.send_body(', (root / 'http_handler_adapters.py').read_text())
        self.assertIn('logger.info("HTTP %d POST %s"', transport_source)
        self.assertIn('logger.warning("HTTP %d %s %s"', transport_source)
        self.assertIn('route = urlsplit(handler.path).path', transport_source)
        logger = logging.getLogger("declan.server")
        previous_level = logger.level
        self.addCleanup(logger.setLevel, previous_level)
        logger.setLevel(logging.INFO)
        logger.info("HTTP 200 POST /api/assist")
        self.assertEqual(declan_logs.recent("INFO")[0]["message"],
                         "HTTP 200 POST /api/assist")

    def test_log_feed_keeps_public_response_shape(self):
        logging.getLogger("declan.server").warning("Test diagnostic")
        item = declan_logs.recent("WARNING")[0]
        self.assertEqual(set(item), {"time", "level", "source", "message"})
        self.assertEqual(item["message"], "Test diagnostic")

    def test_reattaches_handler_after_root_logger_reset(self):
        root = logging.getLogger()
        handler = declan_logs.STATE.handler
        assert handler is not None
        root.removeHandler(handler)
        try:
            declan_logs.install()
            self.assertEqual(sum(item is handler for item in root.handlers), 1)
        finally:
            declan_logs.install()

    def test_install_is_idempotent(self):
        declan_logs.install()
        declan_logs.install()
        self.assertEqual(sum(isinstance(h, declan_logs._Capture)
                             for h in logging.getLogger().handlers), 1)


if __name__ == "__main__":
    unittest.main()
