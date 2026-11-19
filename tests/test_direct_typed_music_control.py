"""Typed music control uses the provider directly, retaining legacy public API."""
import unittest
from unittest.mock import patch

from declan.music import music
from declan.core.execution_results import ExecutionResult, Outcome


class DirectTypedMusicControlTests(unittest.TestCase):
    def test_typed_control_calls_provider_without_legacy_wrapper(self):
        expected = ExecutionResult("Stopped.", Outcome.CONFIRMED)
        with patch.object(music, "_control_provider", return_value=expected) as provider, \
             patch.object(music, "control", side_effect=AssertionError("legacy wrapper used")):
            result = music.control_result(("media_stop", None), None, lambda _: ([], None))
        self.assertIs(result, expected)
        provider.assert_called_once()

    def test_legacy_control_preserves_pair(self):
        expected = ExecutionResult("Stopped.", Outcome.CONFIRMED)
        with patch.object(music, "_control_provider", return_value=expected):
            self.assertEqual(music.control(("media_stop", None), None, lambda _: ([], None)),
                             ("Stopped.", "confirmed"))

    def test_typed_control_rejects_invalid_provider_outcome(self):
        with patch.object(music, "_control_provider", return_value=("Stopped.", "invalid")):
            with self.assertRaises(ValueError):
                music.control_result(("media_stop", None), None, lambda _: ([], None))


if __name__ == "__main__":
    unittest.main()
