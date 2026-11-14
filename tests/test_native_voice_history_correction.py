"""Historical correction must be explicitly confirmed and stale-write protected."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
VIEW = (ROOT / "custom_components/declan_two/voice_review_view.py").read_text()
SERVER = (ROOT / "server.py").read_text()
PANEL = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()

class NativeVoiceCorrectionContract(unittest.TestCase):
    def test_admin_proxy_and_expected_revision(self):
        ast.parse(VIEW)
        self.assertIn('not user.is_admin', VIEW)
        self.assertIn('operation == "correct"', VIEW)
        self.assertIn('set(body) != {"operation", "interaction_id", "assigned_to", "expected_resolution_id", "confirm"}', VIEW)
        self.assertIn('"expected_resolution_id": body["expected_resolution_id"]', VIEW)
        self.assertIn('"current_resolution_id": row.get("current_resolution_id")', VIEW)

    def test_backend_limits_remote_correction_shape(self):
        self.assertIn('body.get("operation") == "correct"', SERVER)
        self.assertIn('body.get("confirm") is not True', SERVER)

    def test_ui_requires_review_revision_and_confirmation(self):
        self.assertIn('!item.current_resolution_id', PANEL)
        self.assertIn("window.confirm('Correct this reviewed recording", PANEL)
        self.assertIn('expected_resolution_id: item.current_resolution_id', PANEL)
        self.assertIn('this.correctVoiceHistory(item, select.value)', PANEL)

if __name__ == "__main__":
    unittest.main()
