"""Verify runtime history retention defaults and invalid overrides."""
import os
import unittest
from unittest.mock import patch

from declan.core.history import retention_seconds


DAY = 24 * 60 * 60


class HistoryRetentionEnvironmentTests(unittest.TestCase):
    def test_unset_retention_defaults_to_thirty_days(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(retention_seconds(), 30 * DAY)

    def test_configured_retention_boundaries(self):
        for days in (1, 7, 30):
            with self.subTest(days=days):
                with patch.dict(os.environ, {"DECLAN_HISTORY_RETENTION_DAYS": str(days)}):
                    self.assertEqual(retention_seconds(), days * DAY)

    def test_invalid_retention_fails_closed(self):
        for value in ("", "0", "31", "-1", "1.5", " 7", "seven"):
            with self.subTest(value=value):
                with patch.dict(os.environ, {"DECLAN_HISTORY_RETENTION_DAYS": value}):
                    with self.assertRaises(ValueError):
                        retention_seconds()


if __name__ == "__main__":
    unittest.main()
