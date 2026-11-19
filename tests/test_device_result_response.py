"""Device result response regression tests."""
import unittest
from unittest.mock import Mock
from declan.ha.device_result_response import device_result_response


class DeviceResultResponseTests(unittest.TestCase):
    def setUp(self):
        self.dispatch = Mock()
        self.dispatch.result.as_legacy_pair.return_value = ("Light is on", "confirmed")
        self.dispatch.status_target = "light.lounge"

    def test_reply(self):
        self.assertEqual(device_result_response(self.dispatch)[0], "Light is on")

    def test_outcome(self):
        self.assertEqual(device_result_response(self.dispatch)[1], "confirmed")

    def test_status_target(self):
        self.assertEqual(device_result_response(self.dispatch)[2], "light.lounge")

    def test_conversion_called_once(self):
        device_result_response(self.dispatch)
        self.dispatch.result.as_legacy_pair.assert_called_once_with()

    def test_status_target_reference_preserved(self):
        target = {"entity_id": "light.lounge"}
        self.dispatch.status_target = target
        self.assertIs(device_result_response(self.dispatch)[2], target)

    def test_missing_status_target(self):
        self.dispatch.status_target = None
        self.assertIsNone(device_result_response(self.dispatch)[2])

    def test_failed_outcome(self):
        self.dispatch.result.as_legacy_pair.return_value = ("Unavailable", "failed")
        self.assertEqual(device_result_response(self.dispatch)[1], "failed")

    def test_empty_reply(self):
        self.dispatch.result.as_legacy_pair.return_value = ("", "confirmed")
        self.assertEqual(device_result_response(self.dispatch)[0], "")

    def test_none_reply(self):
        self.dispatch.result.as_legacy_pair.return_value = (None, "failed")
        self.assertIsNone(device_result_response(self.dispatch)[0])

    def test_conversion_error_propagates(self):
        self.dispatch.result.as_legacy_pair.side_effect = ValueError("bad result")
        with self.assertRaises(ValueError):
            device_result_response(self.dispatch)

    def test_result_reference_preserved(self):
        original = self.dispatch.result
        device_result_response(self.dispatch)
        self.assertIs(self.dispatch.result, original)
