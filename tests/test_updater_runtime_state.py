"""Updater runtime state isolation, release-channel safety and concurrency tests."""

import threading
import unittest
from unittest.mock import patch

from update_results import UpdateJobState
from updater_runtime_state import UpdaterRuntimeState


def selection(commit="a", *, prerelease=False, include_prereleases=False):
    value = {"ref": commit * 40, "commit": commit * 40, "source": "github"}
    if prerelease:
        value["prerelease"] = True
    if include_prereleases:
        value["include_prereleases"] = True
    return value


class UpdaterRuntimeStateTests(unittest.TestCase):
    def test_failed_check_invalidates_previous_selections(self):
        state = UpdaterRuntimeState()
        epoch = state.begin_check()
        self.assertTrue(state.finish_check(epoch, {"1.0.0": selection()}))
        state.begin_check()
        self.assertEqual(state.tags, {})
        with self.assertRaisesRegex(ValueError, "Check for updates"):
            state.claim("1.0.0", "0.9.0", False)

    def test_late_check_cannot_replace_newer_release_choices(self):
        state = UpdaterRuntimeState()
        first = state.begin_check()
        second = state.begin_check()
        self.assertTrue(state.finish_check(second, {"2.0.0": selection("b")}))
        self.assertFalse(state.finish_check(first, {"1.0.0": selection("a")}))
        self.assertEqual(list(state.tags), ["2.0.0"])
        with self.assertRaises(ValueError):
            state.claim("1.0.0", "0.9.0", False)

    def test_concurrent_claims_allow_only_one_install(self):
        state = UpdaterRuntimeState()
        generation = state.begin_check()
        state.finish_check(generation, {"1.0.0": selection()})
        barrier = threading.Barrier(8)
        results = []
        result_lock = threading.Lock()

        def claim():
            barrier.wait(timeout=5)
            try:
                state.claim("1.0.0", "0.9.0", False)
                status = "accepted"
            except ValueError:
                status = "busy"
            with result_lock:
                results.append(status)

        threads = [threading.Thread(target=claim) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(results.count("accepted"), 1)
        self.assertEqual(results.count("busy"), 7)
        self.assertEqual(state.job["state"], UpdateJobState.INSTALLING.value)

    def test_prerelease_channel_cannot_be_reused_after_switch(self):
        state = UpdaterRuntimeState()
        generation = state.begin_check()
        state.finish_check(generation, {"2.0.0-rc.1": selection(prerelease=True, include_prereleases=True)})
        self.assertEqual(state.prerelease_versions(), ["2.0.0-rc.1"])
        with self.assertRaisesRegex(ValueError, "release channel changed"):
            state.claim("2.0.0-rc.1", "1.0.0", False)
        self.assertEqual(state.claim("2.0.0-rc.1", "1.0.0", True)["source"], "github")

    def test_selection_copy_and_status_snapshot_are_detached(self):
        state = UpdaterRuntimeState()
        gen = state.begin_check()
        state.finish_check(gen, {"1.0.0": selection()})
        chosen = state.claim("1.0.0", "0.9.0", False)
        chosen["ref"] = "tampered"
        self.assertEqual(state.tags["1.0.0"]["ref"], "a" * 40)
        result = state.status(enabled=True)
        state.update_job(backup="snapshot")
        self.assertNotIn("backup", result.to_wire())
        self.assertEqual(result.to_wire()["state"], "installing")

    def test_restart_and_failure_states(self):
        state = UpdaterRuntimeState()
        self.assertFalse(state.restart.is_set())
        state.request_restart()
        self.assertTrue(state.restart.is_set())
        self.assertEqual(state.job["state"], "restarting")
        state.update_job(state="failed")
        self.assertEqual(state.status(enabled=False).to_wire()["state"], "failed")

    def test_separate_instances_do_not_share_jobs_or_offers(self):
        first, second = UpdaterRuntimeState(), UpdaterRuntimeState()
        first.finish_check(first.begin_check(), {"1.0.0": selection()})
        first.update_job(state="failed")
        self.assertEqual(second.tags, {})
        self.assertEqual(second.job["state"], "idle")


if __name__ == "__main__":
    unittest.main()
