import sqlite3
import unittest
from datetime import datetime, timezone

from declan.ai.ai_budget import reserve, settle, monthly_reserved


NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")

    def tearDown(self):
        self.db.close()

    def test_reservation_prevents_overspend(self):
        reserve(self.db, limit_micro_usd=100, max_request_micro_usd=60, now=NOW)
        with self.assertRaises(ValueError):
            reserve(self.db, limit_micro_usd=100, max_request_micro_usd=60, now=NOW)
        self.assertEqual(monthly_reserved(self.db, now=NOW), 60)

    def test_settlement_releases_unused_budget(self):
        token = reserve(self.db, limit_micro_usd=100, max_request_micro_usd=60, now=NOW)
        settle(self.db, token, 20)
        self.assertEqual(monthly_reserved(self.db, now=NOW), 20)
        reserve(self.db, limit_micro_usd=100, max_request_micro_usd=60, now=NOW)

    def test_over_ceiling_rejected(self):
        token = reserve(self.db, limit_micro_usd=100, max_request_micro_usd=60, now=NOW)
        with self.assertRaises(ValueError):
            settle(self.db, token, 61)
        self.assertEqual(monthly_reserved(self.db, now=NOW), 60)

    def test_invalid_limits(self):
        with self.assertRaises(ValueError):
            reserve(self.db, limit_micro_usd=0, max_request_micro_usd=1, now=NOW)

    def test_month_isolation(self):
        reserve(self.db, limit_micro_usd=100, max_request_micro_usd=100, now=NOW)
        dec = datetime(2026, 12, 1, tzinfo=timezone.utc)
        self.assertEqual(monthly_reserved(self.db, now=dec), 0)


if __name__ == "__main__":
    unittest.main()
