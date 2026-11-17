"""Request origin and scope regression tests."""
import unittest
from request_origin import request_context


class RequestOriginTests(unittest.TestCase):
    def test_browser_keyboard_scope(self):
        self.assertEqual(request_context("/api/chat", {}),
                         ("browser_keyboard", "browser_keyboard", None, None))

    def test_browser_voice_scope(self):
        self.assertEqual(request_context("/api/chat", {"source": "voice"}),
                         ("browser_voice", "browser_voice", None, None))

    def test_browser_ignores_satellite(self):
        self.assertEqual(request_context("/api/chat", {
            "satellite_id": "assist_satellite.kitchen"}),
            ("browser_keyboard", "browser_keyboard", None, None))

    def test_assist_without_origin_has_no_scope(self):
        self.assertEqual(request_context("/api/assist", {}),
                         ("assist", None, None, None))

    def test_assist_device_user_and_satellite_scope(self):
        self.assertEqual(request_context("/api/assist", {
            "device_id": "device-1", "user_id": "user-1",
            "satellite_id": "assist_satellite.kitchen"}),
            ("assist", ("assist", "device-1", "user-1", "assist_satellite.kitchen"),
             "device-1", "assist_satellite.kitchen"))

    def test_invalid_satellite_dropped(self):
        source, scope, device, satellite = request_context("/api/assist", {
            "device_id": "device-1", "satellite_id": "bad.satellite"})
        self.assertEqual((source, scope, device, satellite),
                         ("assist", ("assist", "device-1", None, None), "device-1", None))

    def test_overlong_origin_dropped(self):
        self.assertEqual(request_context("/api/assist", {
            "device_id": "a" * 129, "user_id": "b" * 129}),
            ("assist", None, None, None))

    def test_valid_satellite_without_device_sets_scope(self):
        self.assertEqual(request_context("/api/assist", {
            "satellite_id": "assist_satellite.bedroom"}),
            ("assist", ("assist", None, None, "assist_satellite.bedroom"),
             None, "assist_satellite.bedroom"))
