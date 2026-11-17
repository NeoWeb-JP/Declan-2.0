"""Routine preview dispatch regression tests."""
import unittest
from unittest.mock import Mock
from routine_preview_dispatch import dispatch_preview


class RoutinePreviewDispatchTests(unittest.TestCase):
    def setUp(self):
        self.detect = Mock(return_value="good night")
        self.preview = Mock(return_value=("Preview ready", "confirmed"))

    def dispatch(self, **overrides):
        args = dict(origin_device="bedroom", satellite="kitchen",
                    detect_phrase=self.detect, preview_routine=self.preview)
        args.update(overrides)
        return dispatch_preview("preview good night", **args)

    def test_preview_result_returned(self):
        self.assertEqual(self.dispatch(), ("Preview ready", "confirmed"))

    def test_phrase_detected(self):
        self.dispatch()
        self.detect.assert_called_once_with("preview good night")

    def test_preview_uses_detected_phrase(self):
        self.dispatch()
        self.assertEqual(self.preview.call_args.args[0], "good night")

    def test_origin_device_preferred(self):
        self.dispatch()
        self.assertEqual(self.preview.call_args.args[1], "bedroom")

    def test_satellite_fallback(self):
        self.dispatch(origin_device=None)
        self.assertEqual(self.preview.call_args.args[1], "kitchen")

    def test_empty_origin_uses_satellite(self):
        self.dispatch(origin_device="")
        self.assertEqual(self.preview.call_args.args[1], "kitchen")

    def test_no_preview_returns_none(self):
        self.detect.return_value = None
        self.assertIsNone(self.dispatch())

    def test_no_preview_does_not_execute(self):
        self.detect.return_value = None
        self.dispatch()
        self.preview.assert_not_called()

    def test_empty_preview_phrase_skips_execution(self):
        self.detect.return_value = ""
        self.assertIsNone(self.dispatch())
        self.preview.assert_not_called()

    def test_preview_handler_none_propagates(self):
        self.preview.return_value = None
        self.assertIsNone(self.dispatch())

    def test_preview_called_once(self):
        self.dispatch()
        self.preview.assert_called_once()
