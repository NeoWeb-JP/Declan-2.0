"""Regression coverage for the bounded native Declan log feed."""
import logging
import unittest
from unittest.mock import patch

import declan_logs


class DeclanLogTests(unittest.TestCase):
    def setUp(self):
        with declan_logs._LOCK:
            declan_logs._ENTRIES.clear()
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

    def test_install_is_idempotent(self):
        declan_logs.install()
        declan_logs.install()
        self.assertEqual(sum(isinstance(h, declan_logs._Capture)
                             for h in logging.getLogger().handlers), 1)


if __name__ == "__main__":
    unittest.main()
