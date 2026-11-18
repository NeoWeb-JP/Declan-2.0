"""Ingress session dispatch regression tests."""
import unittest
from unittest.mock import Mock

from ingress_session_dispatch import suppress_duplicate, load_recent_context, cancel_retry


class IngressSessionDispatchTests(unittest.TestCase):
    def test_capture_preserves_arbitration_dependencies(self):
        handler = object()
        deps = dict(source="assist", satellite="kitchen", session_id="s", arbiter=Mock())
        suppress = Mock(return_value=True)
        self.assertTrue(suppress_duplicate(handler, suppress=suppress, **deps))
        suppress.assert_called_once_with(handler, **deps)

    def test_context_preserves_session_lock_and_idle_window(self):
        deps = dict(session_id="s", scope="room", sessions={}, lock=Mock(),
                    now=10, idle_seconds=60, retrieve=Mock())
        load = Mock(return_value=("lights", "device", "info"))
        self.assertEqual(load_recent_context(load=load, **deps),
                         ("lights", "device", "info"))
        load.assert_called_once_with(**deps)

    def test_cancellation_preserves_recording_and_speaker(self):
        deps = dict(message="cancel", session_id="s", scope="room",
                    speaker="Jaco", lock=Mock(), record=Mock())
        cancel = Mock(return_value="cancelled")
        self.assertEqual(cancel_retry(cancel_pending=cancel, **deps), "cancelled")
        cancel.assert_called_once_with(**deps)


if __name__ == "__main__":
    unittest.main()
