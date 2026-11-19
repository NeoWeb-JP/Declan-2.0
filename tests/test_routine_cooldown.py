"""Routine cooldown concurrency and timing regression tests."""
import threading
import unittest
from declan.turn.routine_cooldown import RoutineCooldown


class RoutineCooldownTests(unittest.TestCase):
    def test_duplicate_within_thirty_seconds(self):
        now = [100.0]
        cooldown = RoutineCooldown(clock=lambda: now[0])
        self.assertTrue(cooldown.claim("morning"))
        now[0] = 129.99
        self.assertFalse(cooldown.claim("morning"))
        now[0] = 130.0
        self.assertTrue(cooldown.claim("morning"))

    def test_keys_are_independent(self):
        cooldown = RoutineCooldown(clock=lambda: 1.0)
        self.assertTrue(cooldown.claim("morning"))
        self.assertTrue(cooldown.claim(("movie", "lounge", "start")))
        self.assertTrue(cooldown.claim(("movie", "bedroom", "start")))
        self.assertFalse(cooldown.claim("morning"))

    def test_concurrent_claims_only_one_wins(self):
        cooldown = RoutineCooldown(clock=lambda: 1.0)
        barrier = threading.Barrier(12)
        results = []
        def claim():
            barrier.wait()
            results.append(cooldown.claim("night"))
        threads = [threading.Thread(target=claim) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 11)


if __name__ == "__main__":
    unittest.main()
