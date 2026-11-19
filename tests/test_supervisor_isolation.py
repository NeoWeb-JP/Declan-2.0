"""A slow maintenance job must not block the supervisor loop or stack up threads."""
import time
import unittest
from threading import Event, Thread

import server_lifecycle


class SingleFlightRunnerTests(unittest.TestCase):
    def test_slow_job_does_not_block_the_caller_and_is_not_stacked(self):
        run = server_lifecycle.single_flight_runner(Thread)
        release, started = Event(), Event()
        calls = []

        def slow():
            calls.append("run")
            started.set()
            release.wait(5)

        begun = time.monotonic()
        self.assertTrue(run("music", slow))
        self.assertLess(time.monotonic() - begun, 0.5)
        self.assertTrue(started.wait(2))
        self.assertFalse(run("music", slow))  # still running: skipped
        self.assertTrue(run("prune", lambda: calls.append("prune")))  # other jobs unaffected
        release.set()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not run("music", lambda: calls.append("again")):
            time.sleep(0.01)
        time.sleep(0.1)
        self.assertEqual(calls.count("run"), 1)
        self.assertIn("again", calls)

    def test_failed_job_frees_its_slot(self):
        run = server_lifecycle.single_flight_runner(Thread)
        done = Event()

        def broken():
            try:
                raise RuntimeError("boom")
            finally:
                done.set()

        self.assertTrue(run("music", broken))
        self.assertTrue(done.wait(2))
        deadline = time.monotonic() + 2
        ran = Event()
        while time.monotonic() < deadline and not run("music", ran.set):
            time.sleep(0.01)
        self.assertTrue(ran.wait(2))


if __name__ == "__main__":
    unittest.main()
