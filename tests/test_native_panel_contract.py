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

    def test_module_url_changes_when_the_panel_changes(self):
        """A cached old panel.js must not survive an upgrade (seen 22 Nov 2026)."""
        import hashlib
        import importlib.util
        import sys
        import tempfile
        from types import ModuleType
        source = (INTEGRATION / "native_panel.py").read_text()
        self.assertIn('module_url=f"{ASSET_PATH}/panel.js?v={version}"', source)
        self.assertIn("async_add_executor_job(panel_version)", source)
        stubs = {name: ModuleType(name) for name in (
            "homeassistant", "homeassistant.components", "homeassistant.components.frontend",
            "homeassistant.components.panel_custom", "homeassistant.components.http")}
        setattr(stubs["homeassistant.components"], "frontend", stubs["homeassistant.components.frontend"])
        setattr(stubs["homeassistant.components"], "panel_custom", stubs["homeassistant.components.panel_custom"])
        setattr(stubs["homeassistant.components.http"], "StaticPathConfig", object)
        saved = {name: sys.modules.get(name) for name in stubs}
        sys.modules.update(stubs)
        try:
            spec = importlib.util.spec_from_file_location("native_panel_under_test", INTEGRATION / "native_panel.py")
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            for name, value in saved.items():
                if value is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = value
        panel = (INTEGRATION / "frontend" / "panel.js").read_bytes()
        self.assertEqual(module.panel_version(), hashlib.sha256(panel).hexdigest()[:12])
        with tempfile.TemporaryDirectory() as folder:
            changed = Path(folder) / "panel.js"
            changed.write_bytes(panel + b"\n")
            self.assertNotEqual(module.panel_version(changed), module.panel_version())
            self.assertEqual(module.panel_version(Path(folder) / "missing.js"), "0")

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
