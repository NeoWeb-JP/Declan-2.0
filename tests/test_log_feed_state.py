"""Bounded, isolated and concurrent log feed state regressions."""

import logging
from concurrent.futures import ThreadPoolExecutor
import unittest

from log_feed_state import LogFeedState


class LogFeedStateTests(unittest.TestCase):
    def test_bounded_storage_and_copy_isolation(self):
        state = LogFeedState(capacity=3)
        for value in range(5):
            state.append({"levelno": logging.INFO, "message": str(value)})
        self.assertEqual([x["message"] for x in state.snapshot(threshold=0, limit=10)],
                         ["4", "3", "2"])
        snapshot = state.snapshot(threshold=0, limit=3)
        snapshot[0]["message"] = "tampered"
        self.assertEqual(state.snapshot(threshold=0, limit=3)[0]["message"], "4")
        self.assertNotIn("levelno", snapshot[0])

    def test_concurrent_writers_do_not_exceed_capacity(self):
        state = LogFeedState(capacity=200)
        def write(value):
            state.append({"levelno": logging.WARNING, "message": str(value)})
        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(write, range(1000)))
        items = state.snapshot(threshold=logging.WARNING, limit=1000)
        self.assertEqual(len(items), 200)
        self.assertEqual(len({item["message"] for item in items}), 200)
        self.assertEqual(state.snapshot(threshold=logging.ERROR, limit=1000), [])

    def test_independent_instances_do_not_share_log_entries(self):
        first, second = LogFeedState(), LogFeedState()
        first.append({"levelno": logging.ERROR, "message": "private"})
        self.assertEqual(second.snapshot(threshold=0, limit=10), [])

    def test_handler_install_idempotent_and_reattaches(self):
        root = logging.getLogger("declan.log-feed-test")
        state = LogFeedState()
        handler = logging.NullHandler()
        self.addCleanup(root.removeHandler, handler)
        state.install(root, lambda: handler)
        state.install(root, lambda: self.fail("should not allocate twice"))
        self.assertEqual(sum(h is handler for h in root.handlers), 1)
        root.removeHandler(handler)
        state.install(root, lambda: self.fail("should reuse prior handler"))
        self.assertIn(handler, root.handlers)


if __name__ == "__main__":
    unittest.main()
