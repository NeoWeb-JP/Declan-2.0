"""Compatibility facade regression tests."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import compatibility_facade as facade
import server


class CompatibilityFacadeTests(unittest.TestCase):
    def test_routine_outcome_preserves_triple(self):
        r = Mock()
        outcome = SimpleNamespace(reply="done", outcome=SimpleNamespace(value="confirmed"))
        self.assertEqual(facade._routine_legacy_triple(outcome, 200, r=r), ("done", "confirmed", 200))

    def test_routine_selection_preserves_none(self):
        r = Mock()
        r.select_routine_result.return_value = None
        self.assertIsNone(facade.select_routine("hello", "kitchen", r=r))

    def test_media_search_preserves_legacy_pair(self):
        r = Mock()
        r.search_media_result.return_value.as_legacy_pair.return_value = ("music", "found")
        self.assertEqual(facade.search_media("music", r=r), ("music", "found"))

    def test_pending_stop_uses_live_result_callback(self):
        r = Mock()
        r.stop_pending_routines_result.return_value = ("result", 200)
        r._routine_legacy_triple.return_value = ("stopped", "ok", 200)
        self.assertEqual(facade.stop_pending_routines(r=r), ("stopped", "ok", 200))
        r._routine_legacy_triple.assert_called_once_with("result", 200)

    def test_transcription_preserves_extra_options(self):
        r = Mock()
        r.traced_transcribe_result.return_value.text = "hello"
        self.assertEqual(facade.traced_transcribe("audio", language="en", r=r), "hello")
        r.traced_transcribe_result.assert_called_once_with("audio", language="en")

    def test_public_wrapper_uses_patched_result(self):
        typed = Mock()
        typed.as_legacy_pair.return_value = ("music", "found")
        with patch.object(server, "search_media_result", return_value=typed):
            self.assertEqual(server.search_media("music"), ("music", "found"))


if __name__ == "__main__":
    unittest.main()
