"""Native learned-intention management is admin-scoped and non-executing."""
from pathlib import Path
import ast
import unittest
ROOT=Path(__file__).resolve().parents[1]
SERVER=(ROOT/"server.py").read_text()
VIEW=(ROOT/"custom_components/declan_two/management_view.py").read_text()
HISTORY=(ROOT/"custom_components/declan_two/history_view.py").read_text()
JS=(ROOT/"custom_components/declan_two/frontend/panel.js").read_text()
class NativeIntentsTests(unittest.TestCase):
    def test_proxy_and_backend_parse(self):
        ast.parse(SERVER)
        ast.parse(VIEW)
        ast.parse(HISTORY)
        self.assertIn('"/api/native/intents"', SERVER)
        self.assertIn('history.edit_intent(body["phrase"], body["target"], body["previous"])', SERVER)
        self.assertIn('history.forget_intent(phrase)', SERVER)
        self.assertIn('history.teach_intent(body["turn_id"], body["target"], UNMATCHED_REPLY)', SERVER)
        self.assertIn('not user.is_admin', VIEW)
        self.assertIn('{"forget", "previous"}', VIEW)
        self.assertIn('"teachable": item.get("teachable") is True', HISTORY)
    def test_ui_edit_forget_teach(self):
        for value in ('class="intents-list"', 'async loadLearnedIntents()', 'async changeLearnedIntent(body)',
                      "window.confirm('Forget the learned command", "this.changeLearnedIntent({phrase, target:next, previous:target})",
                      "this.changeLearnedIntent({turn_id:turn.id, target:target.trim()})"):
            self.assertIn(value, JS)
        self.assertIn('name.textContent = phrase', JS)
        self.assertNotIn('Advanced editing remains in the existing Declan app.', JS)
if __name__=="__main__": unittest.main()
