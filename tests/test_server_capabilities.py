"""Regression coverage for the Declan server capability contract.

These tests execute the actual HTTP handler against a loopback test server.
"""
import json
import threading
import unittest
from http.server import HTTPServer
from urllib.request import urlopen

import server


class CapabilitiesTests(unittest.TestCase):
    def test_loopback_capabilities_have_stable_api_contract(self):
        httpd = HTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(f"http://127.0.0.1:{httpd.server_port}/api/capabilities", timeout=3) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers.get("Cache-Control"), "no-store")
                payload = json.load(response)
            self.assertEqual(payload["api_version"], "1.0")
            self.assertEqual(payload["server_version"], server.RELEASE_VERSION)
            self.assertIn("updates", payload["capabilities"])
            self.assertIn("ha_status", payload["capabilities"])
            self.assertTrue(all(isinstance(value, str) for value in payload["capabilities"]))
        finally:
            httpd.shutdown()
            thread.join(timeout=3)
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
