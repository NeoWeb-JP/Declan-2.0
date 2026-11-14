"""Keep the management status indicator bound to the Declan API, not HA."""
from pathlib import Path
import unittest


PAGE = (Path(__file__).resolve().parents[1] / "index.html").read_text(encoding="utf-8")


class APIStatusIndicatorTests(unittest.TestCase):
    def test_footer_identifies_declan_api(self):
        self.assertIn('id="api-status"', PAGE)
        self.assertIn('Checking Declan API', PAGE)
        self.assertNotIn('id="ha-status"', PAGE)

    def test_status_uses_capabilities_not_home_assistant(self):
        self.assertIn("fetch('./api/capabilities'", PAGE)
        self.assertNotIn("fetch('./api/ha-status'", PAGE)
        self.assertIn("response.ok", PAGE)
        self.assertIn("Array.isArray(result.capabilities)", PAGE)
        self.assertIn("state = 'connected'", PAGE)
        self.assertIn("Declan API unavailable", PAGE)
        self.assertIn("Declan API access denied", PAGE)
        self.assertIn("Declan API incompatible", PAGE)


if __name__ == "__main__":
    unittest.main()
