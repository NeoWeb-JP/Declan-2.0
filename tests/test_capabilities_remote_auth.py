"""Guard the HA integration's read-only remote capabilities authentication."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "server.py").read_text()
GATE = (ROOT / "get_access_gate_http.py").read_text()


class RemoteCapabilitiesAuthTests(unittest.TestCase):
    def test_bearer_exception_is_scoped_to_capabilities(self):
        start = SOURCE.index("    def do_GET(self):")
        end = SOURCE.index("    def do_POST(self):", start)
        block = SOURCE[start:end]
        dispatcher = (ROOT / "get_request_dispatch.py").read_text()
        self.assertIn("get_request_dispatch.dispatch(", block)
        self.assertIn("get_access_gate_http.enforce_access(", dispatcher)
        self.assertIn('handler.path == "/api/capabilities" and len(token) >= 32', GATE)
        self.assertIn('secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode())', GATE)
        self.assertIn('not ingress and not native_settings_auth and not settings_status_auth and not capabilities_auth', GATE)
        self.assertIn('handler.path.startswith("/api/settings/")', GATE)
        self.assertIn('handler.path in {"/api/diagnostics"', GATE)

    def test_does_not_enable_management_with_assist_token(self):
        self.assertNotIn('capabilities_auth or handler.path.startswith', GATE)
        self.assertNotIn('capabilities_auth or handler.path in', GATE)


if __name__ == "__main__":
    unittest.main()
