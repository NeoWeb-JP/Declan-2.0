"""Regression contracts for the first native Home Assistant panel milestone."""
import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "declan_two"


class NativePanelContractTests(unittest.TestCase):
    def test_panel_registers_with_admin_access_and_static_assets(self):
        source = (INTEGRATION / "native_panel.py").read_text()
        ast.parse(source)
        self.assertIn('require_admin=True', source)
        self.assertIn('embed_iframe=False', source)
        self.assertIn('webcomponent_name="declan-two-native-panel"', source)
        self.assertIn('async_register_static_paths', source)
        self.assertIn('async_register_panel', source)
        self.assertIn('hass.data.get(DATA_KEY)', source)

    def test_integration_registers_panel_without_retiring_ingress(self):
        source = (INTEGRATION / "__init__.py").read_text()
        self.assertIn('await async_register_native_panel(hass)', source)
        self.assertIn('async_forward_entry_setups(entry, PLATFORMS)', source)
        manifest = json.loads((INTEGRATION / "manifest.json").read_text())
        self.assertTrue({'frontend', 'panel_custom', 'http'} <= set(manifest['dependencies']))

    def test_frontend_uses_home_assistant_api_and_renders_without_click(self):
        source = (INTEGRATION / "frontend" / "panel.js").read_text()
        self.assertIn("customElements.define('declan-two-native-panel'", source)
        self.assertIn("this._hass.callApi('GET', 'declan_two/capabilities')", source)
        self.assertIn('this.shadowRoot.innerHTML', source)
        self.assertIn('void this.refresh()', source)
        self.assertNotIn('localStorage', source)
        self.assertNotIn('X-Declan-Ingress-Token', source)
        self.assertNotIn('Bearer ', source)


if __name__ == "__main__":
    unittest.main()
