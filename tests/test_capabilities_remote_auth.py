"""Guard the HA integration's read-only remote capabilities authentication."""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "server.py").read_text()


class RemoteCapabilitiesAuthTests(unittest.TestCase):
    def test_bearer_exception_is_scoped_to_capabilities(self):
        start = SOURCE.index("    def do_GET(self):")
        end = SOURCE.index("    def do_POST(self):", start)
        block = SOURCE[start:end]
        gate = (Path(__file__).resolve().parents[1] / "get_access_gate_http.py").read_text()
        self.assertIn("get_access_gate_http.enforce_access(", gate)
        self.assertIn('handler.path == "/api/capabilities" and len(token) >= 32', gate)
        self.assertIn('secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode())', gate)
        self.assertIn('not ingress and not native_settings_auth and not settings_status_auth and not capabilities_auth', gate)
        self.assertIn('handler.path.startswith("/api/settings/")', gate)
        self.assertIn('handler.path in {"/api/diagnostics"', gate)

    def test_does_not_enable_management_with_assist_token(self):
        start = SOURCE.index("    def do_GET(self):")
        end = SOURCE.index("    def do_POST(self):", start)
        block = SOURCE[start:end]
        self.assertNotIn('capabilities_auth or self.path.startswith', gate)
        self.assertNotIn('capabilities_auth or self.path in', gate)


if __name__ == "__main__":
    unittest.main()
