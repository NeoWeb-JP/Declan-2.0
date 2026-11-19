"""wait_for polls finely but keeps the same overall wait window."""
import unittest
from unittest.mock import patch

import music


class WaitForIntervalTests(unittest.TestCase):
    def run_wait(self, ready_after, **kwargs):
        """Return (result, sleeps) where the player is ready on poll number ready_after."""
        polls = []
        sleeps = []

        def request(connection, path, data=None, *, timeout=None):
            polls.append(path)
            return {"state": "ready" if len(polls) >= ready_after else "idle"}

        with patch.object(music, "request", side_effect=request), patch.object(
                music, "sleep", side_effect=sleeps.append):
            result = music.wait_for(("u", {}, None), "media_player.x",
                                    lambda state: state["state"] == "ready", **kwargs)
        return result, sleeps

    def test_ready_player_is_noticed_after_one_short_sleep(self):
        result, sleeps = self.run_wait(2)
        self.assertTrue(result)
        self.assertEqual(sleeps, [music.POLL_INTERVAL])

    def test_window_matches_the_old_one_second_steps(self):
        for attempts in (4, 8, 10, 12):
            result, sleeps = self.run_wait(10 ** 6, attempts=attempts)
            self.assertFalse(result)
            self.assertAlmostEqual(sum(sleeps), attempts - 1)

    def test_single_attempt_never_sleeps(self):
        result, sleeps = self.run_wait(10 ** 6, attempts=1)
        self.assertFalse(result)
        self.assertEqual(sleeps, [])


if __name__ == "__main__":
    unittest.main()
