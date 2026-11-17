"""Early command result precedence regression tests."""
import unittest
from unittest.mock import Mock
from early_command_result import early_command_result


class EarlyCommandResultTests(unittest.TestCase):
    def setUp(self):
        self.timer = Mock()
        self.timer.result.as_legacy_pair.return_value = ("timer", "confirmed")

    def test_preview_wins(self):
        self.assertEqual(early_command_result(("preview", "confirmed"), self.timer), ("preview", "confirmed"))

    def test_timer_not_evaluated_when_preview_present(self):
        early_command_result(("preview", "confirmed"), self.timer)
        self.timer.result.as_legacy_pair.assert_not_called()

    def test_timer_used_without_preview(self):
        self.assertEqual(early_command_result(None, self.timer), ("timer", "confirmed"))

    def test_timer_called_once(self):
        early_command_result(None, self.timer)
        self.timer.result.as_legacy_pair.assert_called_once()

    def test_no_result(self):
        self.assertIsNone(early_command_result(None, None))

    def test_empty_preview_uses_timer(self):
        self.assertEqual(early_command_result((), self.timer), ("timer", "confirmed"))

    def test_false_preview_uses_timer(self):
        self.assertEqual(early_command_result(False, self.timer), ("timer", "confirmed"))

    def test_false_timer_ignored(self):
        self.assertIsNone(early_command_result(None, False))

    def test_preview_object_preserved(self):
        preview = ("preview", "failed")
        self.assertIs(early_command_result(preview, self.timer), preview)

    def test_timer_pair_preserved(self):
        pair = ("timer", "failed")
        self.timer.result.as_legacy_pair.return_value = pair
        self.assertIs(early_command_result(None, self.timer), pair)

    def test_timer_error_propagates(self):
        self.timer.result.as_legacy_pair.side_effect = ValueError("bad timer")
        with self.assertRaises(ValueError):
            early_command_result(None, self.timer)
