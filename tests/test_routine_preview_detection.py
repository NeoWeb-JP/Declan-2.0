"""Routine preview detection regression tests."""
import unittest
from routine_preview_detection import routine_preview_phrase


class RoutinePreviewDetectionTests(unittest.TestCase):
    def test_preview_prefix(self):
        self.assertEqual(routine_preview_phrase("preview good morning"), "good morning")

    def test_dry_run_hyphen(self):
        self.assertEqual(routine_preview_phrase("dry-run good night"), "good night")

    def test_dry_run_space(self):
        self.assertEqual(routine_preview_phrase("dry run movie time"), "movie time")

    def test_prefix_punctuation(self):
        self.assertEqual(routine_preview_phrase("preview: dinner time"), "dinner time")

    def test_no_preview_prefix(self):
        self.assertIsNone(routine_preview_phrase("good morning"))

    def test_empty_preview_target(self):
        self.assertIsNone(routine_preview_phrase("preview"))

    def test_lighting_request_excluded(self):
        self.assertIsNone(routine_preview_phrase("preview turn on kitchen lights"))

    def test_brightness_request_excluded(self):
        self.assertIsNone(routine_preview_phrase("dry-run set brightness"))

    def test_switch_request_excluded(self):
        self.assertIsNone(routine_preview_phrase("preview switch on the fan"))

    def test_partial_lighting_word_not_excluded(self):
        self.assertEqual(routine_preview_phrase("preview lighthouse mode"), "lighthouse mode")

    def test_prefix_must_start_phrase(self):
        self.assertIsNone(routine_preview_phrase("please preview good night"))
