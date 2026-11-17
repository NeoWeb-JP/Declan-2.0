"""Stop command result conversion regression tests."""
import unittest
from unittest.mock import Mock
from stop_result_response import stop_result_response


class StopResultResponseTests(unittest.TestCase):
    def setUp(self):
        self.dispatch = Mock()
        self.dispatch.result.as_legacy_pair.return_value = ("Stopped", "confirmed")
        self.dispatch.routine_status = "stopped"

    def test_reply(self):
        self.assertEqual(stop_result_response(self.dispatch)[0], "Stopped")

    def test_outcome(self):
        self.assertEqual(stop_result_response(self.dispatch)[1], "confirmed")

    def test_status(self):
        self.assertEqual(stop_result_response(self.dispatch)[2], "stopped")

    def test_pair_called_once(self):
        stop_result_response(self.dispatch)
        self.dispatch.result.as_legacy_pair.assert_called_once_with()

    def test_failed_outcome(self):
        self.dispatch.result.as_legacy_pair.return_value = ("Failed", "failed")
        self.assertEqual(stop_result_response(self.dispatch)[1], "failed")

    def test_none_status(self):
        self.dispatch.routine_status = None
        self.assertIsNone(stop_result_response(self.dispatch)[2])

    def test_empty_reply(self):
        self.dispatch.result.as_legacy_pair.return_value = ("", "confirmed")
        self.assertEqual(stop_result_response(self.dispatch)[0], "")

    def test_none_reply(self):
        self.dispatch.result.as_legacy_pair.return_value = (None, "failed")
        self.assertIsNone(stop_result_response(self.dispatch)[0])

    def test_status_preserved_as_object(self):
        status = {"reason": "cancelled"}
        self.dispatch.routine_status = status
        self.assertIs(stop_result_response(self.dispatch)[2], status)

    def test_conversion_exception_propagates(self):
        self.dispatch.result.as_legacy_pair.side_effect = ValueError("bad result")
        with self.assertRaises(ValueError):
            stop_result_response(self.dispatch)

    def test_result_object_not_mutated(self):
        original = self.dispatch.result
        stop_result_response(self.dispatch)
        self.assertIs(self.dispatch.result, original)
