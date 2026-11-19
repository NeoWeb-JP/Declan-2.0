"""History pagination rejects malformed cursors and unbounded page sizes."""

import tempfile
import unittest
from pathlib import Path

import history


class HistoryPaginationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        original = history.DATABASE
        self.addCleanup(setattr, history, "DATABASE", original)
        history.DATABASE = Path(self.directory.name) / "history.sqlite3"

    def test_invalid_page_sizes_are_rejected(self):
        for limit in (0, -1, 501, True, 1.5, "50", [], {}):
            with self.subTest(limit=limit), self.assertRaisesRegex(ValueError, "page size"):
                history.recent(limit=limit)

    def test_invalid_cursors_are_rejected(self):
        for cursor in (0, -1, True, 1.5, "3", [], {}):
            with self.subTest(cursor=cursor), self.assertRaisesRegex(ValueError, "cursor"):
                history.recent(before=cursor)

    def test_valid_pagination_preserves_order_and_optional_unlimited(self):
        first = history.record("s", "assist", "first", "ok")
        second = history.record("s", "assist", "second", "ok")
        third = history.record("s", "assist", "third", "ok")
        self.assertEqual([row["id"] for row in history.recent(limit=2)], [third, second])
        self.assertEqual([row["id"] for row in history.recent(before=third, limit=2)], [second, first])
        self.assertEqual([row["id"] for row in history.recent(limit=None)], [third, second, first])


if __name__ == "__main__":
    unittest.main()
