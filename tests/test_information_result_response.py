"""Information result conversion regression tests."""
import unittest
from unittest.mock import Mock
from information_result_response import information_result_response


class InformationResultResponseTests(unittest.TestCase):
    def setUp(self):
        self.dispatch = Mock()
        self.dispatch.result.as_legacy_pair.return_value = ("It is 8 o'clock", "confirmed")
        self.dispatch.information_context = ("time", None, None)

    def test_reply(self):
        self.assertEqual(information_result_response(self.dispatch)[0], "It is 8 o'clock")

    def test_outcome(self):
        self.assertEqual(information_result_response(self.dispatch)[1], "confirmed")

    def test_context(self):
        self.assertEqual(information_result_response(self.dispatch)[2], ("time", None, None))

    def test_conversion_called_once(self):
        information_result_response(self.dispatch)
        self.dispatch.result.as_legacy_pair.assert_called_once_with()

    def test_context_reference_preserved(self):
        context = {"question": "weather", "area": "home"}
        self.dispatch.information_context = context
        self.assertIs(information_result_response(self.dispatch)[2], context)

    def test_missing_context_preserved(self):
        self.dispatch.information_context = None
        self.assertIsNone(information_result_response(self.dispatch)[2])

    def test_failed_outcome(self):
        self.dispatch.result.as_legacy_pair.return_value = ("Unavailable", "failed")
        self.assertEqual(information_result_response(self.dispatch)[1], "failed")

    def test_empty_reply(self):
        self.dispatch.result.as_legacy_pair.return_value = ("", "confirmed")
        self.assertEqual(information_result_response(self.dispatch)[0], "")

    def test_none_reply(self):
        self.dispatch.result.as_legacy_pair.return_value = (None, "failed")
        self.assertIsNone(information_result_response(self.dispatch)[0])

    def test_conversion_error_propagates(self):
        self.dispatch.result.as_legacy_pair.side_effect = ValueError("bad response")
        with self.assertRaises(ValueError):
            information_result_response(self.dispatch)

    def test_original_result_reference_preserved(self):
        original = self.dispatch.result
        information_result_response(self.dispatch)
        self.assertIs(self.dispatch.result, original)
