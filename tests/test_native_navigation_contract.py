"""Guard native navigation and staged migration without HA installed."""
from pathlib import Path
import unittest

JS = (Path(__file__).resolve().parents[1] / "custom_components" / "declan_two" / "frontend" / "panel.js").read_text()


class NativeNavigationTests(unittest.TestCase):
    def test_hidden_page_menu_has_matching_panels(self):
        self.assertIn('class="page-navigation" aria-label="Declan pages" hidden', JS)
        for name in ("overview", "conversations", "players", "settings", "updates"):
            with self.subTest(page=name):
                self.assertIn(f'data-page="{name}"', JS)
                self.assertIn(f'id="panel-{name}"', JS)
        self.assertIn("this.selectTab(button.dataset.page)", JS)

    def test_voice_review_is_in_conversation_timeline(self):
        self.assertIn('class="timeline-list"', JS)
        self.assertIn('data-page="conversations"', JS)
        self.assertIn('class="overview-chat-heading"', JS)
        self.assertIn('class="voices-list"', JS)
        self.assertNotIn('id="tab-voices"', JS)

    def test_mobile_and_accessibility(self):
        self.assertIn('aria-label="Open Declan pages"', JS)
        self.assertIn("selectTab(name)", JS)
        self.assertIn("panel.hidden = panel.id !== 'panel-' + name", JS)
        self.assertIn("this.shadowRoot.innerHTML", JS)
        self.assertIn(".page-navigation", JS)

    def test_native_management_replaces_old_app(self):
        self.assertIn("async loadLearnedIntents()", JS)
        self.assertIn("async previewSettingsImport()", JS)
        self.assertIn("async checkUpdates()", JS)
        self.assertIn("async installUpdate()", JS)
        self.assertIn("async loadUpdateStatus()", JS)
        self.assertNotIn("Use the existing Declan updater for now.", JS)
        self.assertNotIn("X-Declan-Ingress-Token", JS)
        self.assertNotIn("Bearer ", JS)
        self.assertIn("this._hass.callApi('GET', 'declan_two/capabilities')", JS)


if __name__ == "__main__":
    unittest.main()
