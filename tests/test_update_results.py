"""Updater busy decisions stay typed while public status fields remain lossless."""
from typing import Any
from pathlib import Path
import unittest
from unittest.mock import patch

import updates
from update_results import UpdateJobState, UpdateStatusResult


class UpdateResultTests(unittest.TestCase):
    def test_status_snapshots_are_frozen_isolated_and_lossless(self):
        fields: dict[str, Any]
        for state in (*UpdateJobState, "future_state", None):
            raw = state.value if isinstance(state, UpdateJobState) else state
            fields = {"state": raw, "version": "1.2.3", "backup": "backup", "extra": {"kept": [1]}}
            with self.subTest(state=state), patch.object(updates.RUNTIME, "job", fields), patch.object(updates, "layout", return_value=None):
                result = updates.status_result()
                self.assertIs(result.state, state if isinstance(state, UpdateJobState) else None)
                self.assertIs(result.active, state in (UpdateJobState.INSTALLING, UpdateJobState.RESTARTING))
                self.assertEqual(result.to_wire(), {"enabled": False, **fields})
                self.assertEqual(updates.status(), result.to_wire())
                with self.assertRaises(AttributeError):
                    setattr(result, "state", UpdateJobState.FAILED)
                fields["extra"]["kept"].append(2)
                wire = result.to_wire()
                wire["extra"]["kept"].append(3)
                self.assertEqual(result.to_wire()["extra"], {"kept": [1]})

    def test_queue_uses_typed_busy_decision_and_preserves_thread_arguments(self):
        for state in UpdateJobState:
            job = {"state": state.value}
            with self.subTest(state=state), patch.object(updates.RUNTIME, "job", job), \
                 patch.object(updates, "layout", return_value=Path("/fixture")), \
                 patch.object(updates.RUNTIME, "tags", {"1.2.3": {"ref": "commit"}}), \
                 patch.object(updates, "Thread") as thread:
                if state in (UpdateJobState.INSTALLING, UpdateJobState.RESTARTING):
                    with self.assertRaisesRegex(ValueError, "already in progress"):
                        updates.queue("1.2.3", "1.0.0")
                    thread.assert_not_called()
                else:
                    updates.queue("1.2.3", "1.0.0")
                    self.assertEqual(job, {"state": "installing", "version": "1.2.3"})
                    self.assertIs(type(job["state"]), str)
                    thread.assert_called_once_with(target=updates.install,
                        args=(Path("/fixture"), "1.2.3", {"ref": "commit"}), daemon=True)
                    thread.return_value.start.assert_called_once()

    def test_unknown_status_is_not_relabelled_as_a_known_state(self):
        result = UpdateStatusResult({"state": "INSTALLING", "enabled": True})
        self.assertIsNone(result.state)
        self.assertFalse(result.active)
        self.assertEqual(result.to_wire(), {"state": "INSTALLING", "enabled": True})
