"""Active routine registry lifecycle and concurrency tests."""
import threading
import unittest

from active_routine_registry import ActiveRoutineRegistry


class ActiveRoutineRegistryTests(unittest.TestCase):
    def test_register_and_release(self):
        registry = ActiveRoutineRegistry()
        with registry.track("morning", "script.morning"):
            self.assertEqual(registry.snapshot(), {"morning": "script.morning"})
        self.assertEqual(registry.snapshot(), {})

    def test_exception_releases_registration(self):
        registry = ActiveRoutineRegistry()
        with self.assertRaisesRegex(RuntimeError, "failure"):
            with registry.track("night", "script.night"):
                raise RuntimeError("failure")
        self.assertEqual(registry.snapshot(), {})

    def test_snapshot_is_detached(self):
        registry = ActiveRoutineRegistry()
        with registry.track("movie", "script.movie"):
            snapshot = registry.snapshot()
            snapshot.clear()
            self.assertEqual(registry.snapshot(), {"movie": "script.movie"})

    def test_overlapping_different_names(self):
        registry = ActiveRoutineRegistry()
        barrier = threading.Barrier(2)
        snapshots_taken = threading.Barrier(2)
        results = []
        def run(name):
            with registry.track(name, "script." + name):
                barrier.wait(timeout=5)
                results.append(registry.snapshot())
                snapshots_taken.wait(timeout=5)
        threads = [threading.Thread(target=run, args=(name,)) for name in ("morning", "night")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(len(results), 2)
        self.assertTrue(all(len(snapshot) == 2 for snapshot in results))

    def test_old_completion_does_not_remove_replacement(self):
        registry = ActiveRoutineRegistry()
        first = registry.track("movie", "script.first")
        second = registry.track("movie", "script.second")
        first.__enter__()
        try:
            second.__enter__()
            try:
                first.__exit__(None, None, None)
                self.assertEqual(registry.snapshot(), {"movie": "script.second"})
            finally:
                second.__exit__(None, None, None)
        finally:
            # Both exits are idempotent only when the context is still open.
            pass
        self.assertEqual(registry.snapshot(), {})


if __name__ == "__main__":
    unittest.main()
