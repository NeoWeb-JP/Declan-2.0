"""Regression coverage for the bounded native Declan log feed."""
import io
import logging
import unittest
from unittest.mock import patch

from declan.core import declan_logs


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

    def test_server_event_log_reaches_the_panel_feed(self):
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

    def test_install_also_sends_declan_warnings_to_the_journal(self):
        self.assertEqual(sum(isinstance(h, declan_logs._Journal)
                             for h in logging.getLogger().handlers), 1)
        stream = io.StringIO()
        handler = declan_logs._Journal(stream)
        logger = logging.getLogger("declan.ai.ai_fallback_dispatch")
        logger.addHandler(handler)
        try:
            logger.warning("AI fallback stopped before changing devices: api_key=sk-secret")
            logger.info("routine detail")
            logging.getLogger("unrelated_integration").addHandler(handler)
            logging.getLogger("unrelated_integration").warning("noise")
        finally:
            logger.removeHandler(handler)
            logging.getLogger("unrelated_integration").removeHandler(handler)
        output = stream.getvalue()
        self.assertIn("WARNING declan.ai.ai_fallback_dispatch: AI fallback stopped", output)
        self.assertNotIn("sk-secret", output)
        self.assertNotIn("routine detail", output)
        self.assertNotIn("noise", output)


if __name__ == "__main__":
    unittest.main()
