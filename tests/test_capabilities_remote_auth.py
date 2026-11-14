"""Guard the HA integration's read-only remote capabilities authentication."""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "server.py").read_text()


class RemoteCapabilitiesAuthTests(unittest.TestCase):
    def test_bearer_exception_is_scoped_to_capabilities(self):
        start = SOURCE.index("    def do_GET(self):")
        end = SOURCE.index("    def do_POST(self):", start)
        block = SOURCE[start:end]
        self.assertIn('self.path == "/api/capabilities" and len(token) >= 32', block)
        self.assertIn('secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode())', block)
        self.assertIn('not ingress and not native_settings_auth and not settings_status_auth and not capabilities_auth', block)
        self.assertIn('self.path.startswith("/api/settings/")', block)
        self.assertIn('self.path in {"/api/diagnostics"', block)

    def test_does_not_enable_management_with_assist_token(self):
        start = SOURCE.index("    def do_GET(self):")
        end = SOURCE.index("    def do_POST(self):", start)
        block = SOURCE[start:end]
        self.assertNotIn('capabilities_auth or self.path.startswith', block)
        self.assertNotIn('capabilities_auth or self.path in', block)


if __name__ == "__main__":
    unittest.main()
