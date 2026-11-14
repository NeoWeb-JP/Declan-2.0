"""Guard native navigation and staged migration without HA installed."""
from pathlib import Path
import unittest

JS = (Path(__file__).resolve().parents[1] / "custom_components" / "declan_two" / "frontend" / "panel.js").read_text()


class NativeNavigationTests(unittest.TestCase):
    def test_each_tab_has_matching_panel(self):
        for name in ("overview", "conversations", "players", "settings", "updates"):
            with self.subTest(tab=name):
                self.assertIn(f'id="tab-{name}"', JS)
                self.assertIn(f'id="panel-{name}"', JS)
                self.assertIn(f'aria-controls="panel-{name}"', JS)
                self.assertIn(f'aria-labelledby="tab-{name}"', JS)

    def test_voice_review_is_in_conversation_timeline(self):
        self.assertIn('class="timeline-list"', JS)
        self.assertIn('id="tab-conversations"', JS)
        self.assertIn('class="overview-chat-heading"', JS)
        self.assertIn('class="voices-list"', JS)
        self.assertNotIn('id="tab-voices"', JS)

    def test_mobile_and_accessibility(self):
        self.assertIn('role="tablist"', JS)
        self.assertIn("selectTab(name)", JS)
        self.assertIn("panel.hidden = panel.id !== 'panel-' + name", JS)
        self.assertIn("event.key === 'ArrowRight'", JS)
        self.assertIn("event.key === 'Home'", JS)
        self.assertIn("overflow-x:auto", JS)
        self.assertIn("this.shadowRoot.innerHTML", JS)

    def test_unmigrated_features_remain_in_existing_app(self):
        self.assertIn("existing Declan app", JS)
        self.assertIn("async checkUpdates()", JS)
        self.assertIn("async installUpdate()", JS)
        self.assertIn("async loadUpdateStatus()", JS)
        self.assertNotIn("Use the existing Declan updater for now.", JS)
        self.assertNotIn("X-Declan-Ingress-Token", JS)
        self.assertNotIn("Bearer ", JS)
        self.assertIn("this._hass.callApi('GET', 'declan_two/capabilities')", JS)


if __name__ == "__main__":
    unittest.main()
