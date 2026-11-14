"""Exercise the actual native voice speaker-name validation expressions."""
import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEW = (ROOT / "custom_components/declan_two/voice_review_view.py").read_text()
JS = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()


class NativeSpeakerValidationTests(unittest.TestCase):
    def test_proxy_pattern_accepts_real_names(self):
        tree = ast.parse(VIEW)
        patterns = [
            node.args[0].value for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "fullmatch"
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ]
        speaker_patterns = [p for p in patterns if "{0,39}" in p]
        self.assertEqual(len(speaker_patterns), 1)
        pattern = speaker_patterns[0]
        for name in ("Edd", "Jaco", "Mary Jane", "O'Neil", "Élodie"):
            with self.subTest(name=name):
                self.assertIsNotNone(re.fullmatch(pattern, name))
        for name in ("", "123", "_Edd", "Edd!", "E" * 41):
            with self.subTest(invalid=name):
                self.assertIsNone(re.fullmatch(pattern, name))

    def test_browser_pattern_has_real_unicode_escapes(self):
        self.assertIn(r"/^[\p{L}][\p{L}\p{N}_ '\u2019-]{0,39}$/u", JS)
        self.assertNotIn(r"/^[\\p{L}][\\p{L}\\p{N}_ '\\u2019-]{0,39}$/u", JS)


if __name__ == "__main__":
    unittest.main()
