"""Voice review is authenticated with tightly scoped pending-match writes."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
POST_INGRESS = (ROOT / "post_ingress_orchestration.py").read_text()
SERVER = (ROOT / "server.py").read_text()
ACCESS = (ROOT / "declan" / "voice" / "voicepipeline_access_http.py").read_text()
VIEW = (ROOT / "custom_components/declan_two/voice_review_view.py").read_text()
JS = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()
INIT = (ROOT / "custom_components/declan_two/__init__.py").read_text()


class VoiceReviewContractTests(unittest.TestCase):
    def test_backend_exception_limits_remote_writes(self):
        get = SERVER[SERVER.index("    def do_GET(self):"):SERVER.index("    def do_POST(self):")]
        self.assertIn('http_handler_adapters.do_GET(', get)
        self.assertIn('get_request_dispatch.dispatch(', (__import__("pathlib").Path(__file__).resolve().parents[1] / "http_handler_adapters.py").read_text())
        self.assertIn('get_access_gate_http.enforce_access(', (ROOT / 'get_request_dispatch.py').read_text())
        self.assertIn('handler.path == "/api/voicepipeline"', (ROOT / "get_access_gate_http.py").read_text())
        self.assertIn('not voice_review_auth', (ROOT / "get_access_gate_http.py").read_text())
        ast.parse(ACCESS)
        self.assertIn("r.post_payload_validation.read_authorized_body(", POST_INGRESS)
        self.assertIn("voicepipeline_access_http.enforce_access(", (ROOT / "post_payload_validation.py").read_text())
        self.assertIn('operation not in {"resolve", "audio", "history", "correct"}', ACCESS)
        self.assertIn('body.get("action") not in {"confirm", "assign", "dismiss", "enrol"}', ACCESS)
        self.assertIn('return set(body) != {"operation", "interaction_id"}', ACCESS)
        self.assertIn('return set(body) != {"operation"}', ACCESS)

    def test_ha_view_requires_admin_and_scopes_writes(self):
        ast.parse(VIEW)
        self.assertIn('requires_auth = True', VIEW)
        self.assertIn('not user.is_admin', VIEW)
        self.assertIn('allow_redirects=False', VIEW)
        self.assertIn('"Cache-Control": "no-store"', VIEW)
        self.assertIn('async def post(', VIEW)
        self.assertIn('action not in {"confirm", "assign", "dismiss", "enrol"}', VIEW)
        self.assertIn('body.get("confirm") is not True', VIEW)
        self.assertIn('"enrol"', VIEW)
        self.assertIn('DeclanVoiceReviewView()', INIT)

    def test_ui_displays_plain_text_and_review_actions(self):
        self.assertIn("this._hass.callApi('GET', 'declan_two/voice-review')", JS)
        self.assertIn("summary.textContent = (item.transcript || '(No transcript)')", JS)
        self.assertIn('name.textContent = profile.name', JS)
        self.assertNotIn('transcript.innerHTML', JS)
        self.assertIn("this._hass.callApi('POST', 'declan_two/voice-review'", JS)


if __name__ == "__main__":
    unittest.main()
