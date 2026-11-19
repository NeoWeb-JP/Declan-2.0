"""Timer schema state lifecycle and concurrent initialisation regressions."""

import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from declan.timers.timer_schema_state import TimerSchemaState


class TimerSchemaStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "nested" / "timers.sqlite3"
        self.state = TimerSchemaState()
        self.calls = 0

    def create_schema(self):
        self.calls += 1
        self.path.touch()

    def test_repeated_calls_reuse_same_file_identity(self):
        self.state.ensure(self.path, self.create_schema)
        self.state.ensure(self.path, self.create_schema)
        self.assertEqual(self.calls, 1)

    def test_replaced_database_requires_initialisation(self):
        self.state.ensure(self.path, self.create_schema)
        self.path.unlink()
        self.state.ensure(self.path, self.create_schema)
        self.assertEqual(self.calls, 2)

    def test_failure_does_not_mark_initialised(self):
        def fail():
            raise OSError("schema failure")
        with self.assertRaisesRegex(OSError, "schema failure"):
            self.state.ensure(self.path, fail)
        self.state.ensure(self.path, self.create_schema)
        self.assertEqual(self.calls, 1)

    def test_concurrent_initialisation_runs_once(self):
        start = threading.Barrier(8)
        failures = []
        failure_lock = threading.Lock()

        def worker():
            try:
                start.wait(timeout=5)
                self.state.ensure(self.path, self.create_schema)
            except Exception as error:
                with failure_lock:
                    failures.append(error)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(self.calls, 1)

    def test_instances_do_not_share_initialisation_cache(self):
        self.state.ensure(self.path, self.create_schema)
        TimerSchemaState().ensure(self.path, self.create_schema)
        self.assertEqual(self.calls, 2)


if __name__ == "__main__":
    unittest.main()
