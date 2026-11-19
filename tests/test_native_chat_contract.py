"""Guard the native chat authentication and input/output boundaries."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
AUTH = (ROOT / "post_origin_auth_http.py").read_text()
BACKEND = (ROOT / "server.py").read_text()
VIEW = (ROOT / "custom_components/declan_two/chat_view.py").read_text()
INIT = (ROOT / "custom_components/declan_two/__init__.py").read_text()
JS = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()


class NativeChatContractTests(unittest.TestCase):
    def test_backend_token_exception_is_only_for_chat_post(self):
        block = BACKEND[BACKEND.index("    def handle_post(self):"):BACKEND.index("    def do_GET(self):")] if BACKEND.index("    def handle_post(self):") < BACKEND.index("    def do_GET(self):") else BACKEND[BACKEND.index("    def handle_post(self):"):]
        ast.parse(AUTH)
        self.assertIn("post_entry_gates.enforce(", block)
        self.assertIn("post_request_entry.enforce_preflight(", (ROOT / "post_entry_gates.py").read_text())
        self.assertIn("post_request_preflight.enforce(", (ROOT / "post_request_entry.py").read_text())
        self.assertIn("post_origin_auth_http.enforce_access,", block)
        self.assertIn('"/api/chat"', AUTH)
        self.assertIn('len(token) >= 32', AUTH)
        self.assertIn('secrets.compare_digest(', AUTH)
        self.assertIn('or ingress:', AUTH)

    def test_proxy_is_admin_only_and_validates_message(self):
        ast.parse(VIEW)
        self.assertIn('requires_auth = True', VIEW)
        self.assertIn('not user.is_admin', VIEW)
        self.assertIn('len(message.strip()) <= 1000', VIEW)
        self.assertIn('allow_redirects=False', VIEW)
        self.assertIn('timeout=aiohttp.ClientTimeout(total=45)', VIEW)
        self.assertIn('"Cache-Control": "no-store"', VIEW)
        self.assertIn('DeclanChatView()', INIT)

    def test_chat_does_not_inject_html_or_expose_token(self):
        self.assertIn("this._hass.callApi('POST', 'declan_two/chat'", JS)
        self.assertIn('question.textContent = message', JS)
        self.assertIn('reply.textContent = result.reply', JS)
        self.assertNotIn('reply.innerHTML', JS)
        self.assertNotIn('Bearer ', JS)
        self.assertIn('this._chatSession', JS)


if __name__ == "__main__":
    unittest.main()
