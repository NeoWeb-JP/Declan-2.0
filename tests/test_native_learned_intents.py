"""Native learned-intention management is admin-scoped and non-executing."""
from pathlib import Path
import ast
import unittest
ROOT=Path(__file__).resolve().parents[1]
POST_INGRESS = (ROOT / "post_ingress_orchestration.py").read_text()
SERVER=(ROOT/"server.py").read_text()
TRAINING=(ROOT/"native_training_post.py").read_text()
ROUTES=(ROOT/"training_history_post.py").read_text()
VIEW=(ROOT/"custom_components/declan_two/management_view.py").read_text()
HISTORY=(ROOT/"custom_components/declan_two/history_view.py").read_text()
JS=(ROOT/"custom_components/declan_two/frontend/panel.js").read_text()
class NativeIntentsTests(unittest.TestCase):
    def test_proxy_and_backend_parse(self):
        ast.parse(SERVER)
        ast.parse(TRAINING)
        ast.parse(ROUTES)
        ast.parse(VIEW)
        ast.parse(HISTORY)
        self.assertIn('"/api/native/intents"', ROUTES)
        self.assertIn("r.post_body_routing.dispatch(", POST_INGRESS)
        self.assertIn("training_history_post.handles(handler.path)", (ROOT / "post_body_routing.py").read_text())
        self.assertIn("native_training_post.handle_native_intents(", ROUTES)
        self.assertIn('history.edit_intent(body["phrase"], body["target"], body["previous"])', TRAINING)
        self.assertIn('history.forget_intent(phrase)', TRAINING)
        self.assertIn('history.teach_intent(body["turn_id"], body["target"], unmatched_reply)', TRAINING)
        self.assertIn('not user.is_admin', VIEW)
        self.assertIn('{"forget", "previous"}', VIEW)
        self.assertIn('"teachable": item.get("teachable") is True', HISTORY)
    def test_training_backend_retained_but_no_duplicate_history_list(self):
        # The learned-intent API remains for issue #98; management UI is deliberately
        # not embedded in the rolling seven-day voice-review page.
        self.assertIn('async loadLearnedIntents()', JS)
        self.assertIn('async changeLearnedIntent(body)', JS)
        self.assertIn("this.changeLearnedIntent({phrase, target:next, previous:target})", JS)
        history_panel = JS.split('id="panel-conversations"', 1)[1].split('id="panel-players"', 1)[0]
        self.assertNotIn('class="intents-list"', history_panel)
        self.assertNotIn('Saved phrase corrections', history_panel)
        self.assertIn("train.disabled = !verified;", JS)
        self.assertIn("this._recordingTurnLinks", JS)
        self.assertNotIn('Advanced editing remains in the existing Declan app.', JS)

if __name__=="__main__":
    unittest.main()
