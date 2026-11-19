"""Playlist runtime ownership, concurrent refresh claims and recovery."""

from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import Mock, patch

from declan.music import spotify_playlists
from declan.music.playlist_refresh_state import PlaylistRefreshState


class PlaylistRefreshStateTests(unittest.TestCase):
    def test_duplicate_refresh_claim_is_busy_until_finish(self):
        state = PlaylistRefreshState()
        self.assertTrue(state.claim("country"))
        self.assertFalse(state.claim("rock"))
        self.assertEqual(state.snapshot()["category"], "country")
        state.failure("Spotify rate limit reached (429).")
        state.finish("2026-11-18T12:00:00+00:00")
        self.assertEqual(state.snapshot()["error"], "Spotify rate limit reached (429).")
        self.assertTrue(state.claim("rock"))
        self.assertEqual(state.snapshot(), {
            "running": True, "category": "rock", "error": None, "completed": None,
        })

    def test_concurrent_claims_allow_one_worker(self):
        state = PlaylistRefreshState()
        with ThreadPoolExecutor(max_workers=10) as executor:
            claims = list(executor.map(state.claim, ["country"] * 10))
        self.assertEqual(claims.count(True), 1)
        self.assertEqual(claims.count(False), 9)

    def test_snapshots_cannot_modify_internal_status(self):
        state = PlaylistRefreshState()
        state.claim("country")
        status = state.snapshot()
        status["running"] = False
        status["category"] = "rock"
        self.assertEqual(state.snapshot()["category"], "country")
        self.assertTrue(state.snapshot()["running"])

    def test_separate_instances_do_not_share_refresh_slots(self):
        first, second = PlaylistRefreshState(), PlaylistRefreshState()
        self.assertTrue(first.claim("country"))
        self.assertFalse(second.snapshot()["running"])
        self.assertTrue(second.claim("rock"))

    def test_failed_thread_start_releases_refresh_slot(self):
        state = PlaylistRefreshState()
        worker = Mock()
        worker.return_value.start.side_effect = RuntimeError("no thread")
        with patch.object(spotify_playlists, "RUNTIME", state), \
             patch.object(spotify_playlists, "load", return_value={"country": {}}), \
             patch.object(spotify_playlists, "Thread", worker):
            with self.assertRaisesRegex(RuntimeError, "no thread"):
                spotify_playlists.start_refresh("country", Mock())
            self.assertFalse(state.snapshot()["running"])
            self.assertIn("RuntimeError", state.snapshot()["error"])
            self.assertIsNotNone(state.snapshot()["completed"])
            worker.return_value.start.side_effect = None
            with patch.object(spotify_playlists, "listing", return_value={"ok": True}):
                self.assertEqual(spotify_playlists.start_refresh("country", Mock()), {"ok": True})
            self.assertTrue(state.snapshot()["running"])
            self.assertEqual(worker.call_count, 2)

    def test_existing_refresh_returns_busy_snapshot_without_second_worker(self):
        state = PlaylistRefreshState()
        state.claim("country")
        with patch.object(spotify_playlists, "RUNTIME", state), \
             patch.object(spotify_playlists, "load", return_value={"country": {}, "rock": {}}), \
             patch.object(spotify_playlists, "Thread") as thread:
            result = spotify_playlists.start_refresh("rock", Mock())
        self.assertEqual(result["refresh"]["category"], "country")
        self.assertEqual(result["max_playlists"], spotify_playlists.CAPACITY)
        thread.assert_not_called()


if __name__ == "__main__":
    unittest.main()
