"""Process-local music runtime ownership and skip-throttle regressions."""

import threading
import unittest

from declan.music.music_runtime_state import MusicRuntimeState


class MusicRuntimeStateTests(unittest.TestCase):
    def test_blacklist_skips_are_throttled_per_player(self):
        state = MusicRuntimeState()
        with state.handoff:
            self.assertTrue(state.allow_blacklist_skip("media_player.kitchen", 100))
            self.assertFalse(state.allow_blacklist_skip("media_player.kitchen", 109.99))
            self.assertTrue(state.allow_blacklist_skip("media_player.bedroom", 109.99))
            self.assertTrue(state.allow_blacklist_skip("media_player.kitchen", 110))
        self.assertEqual(state.recent_blacklist_skips["media_player.kitchen"], 120)

    def test_shared_handoff_serialises_music_operations(self):
        state = MusicRuntimeState()
        self.assertTrue(state.handoff.acquire(blocking=False))
        try:
            self.assertFalse(state.handoff.acquire(blocking=False))
        finally:
            state.handoff.release()
        self.assertTrue(state.handoff.acquire(blocking=False))
        state.handoff.release()

    def test_token_lock_is_independent_of_music_handoff(self):
        state = MusicRuntimeState()
        self.assertTrue(state.handoff.acquire(blocking=False))
        try:
            self.assertTrue(state.spotify_token_lock.acquire(blocking=False))
            state.spotify_token_lock.release()
        finally:
            state.handoff.release()

    def test_instances_do_not_share_token_or_skip_state(self):
        first = MusicRuntimeState()
        second = MusicRuntimeState()
        first.spotify_token = (("id", "secret"), "token", 1000)
        with first.handoff:
            first.allow_blacklist_skip("media_player.kitchen", 100)
        self.assertIsNone(second.spotify_token)
        self.assertEqual(second.recent_blacklist_skips, {})

    def test_concurrent_skip_reservation_allows_exactly_one(self):
        state = MusicRuntimeState()
        barrier = threading.Barrier(8)
        results = []
        results_lock = threading.Lock()

        def reserve():
            barrier.wait(timeout=5)
            with state.handoff:
                allowed = state.allow_blacklist_skip("media_player.kitchen", 100)
            with results_lock:
                results.append(allowed)

        workers = [threading.Thread(target=reserve) for _ in range(8)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 7)


if __name__ == "__main__":
    unittest.main()
