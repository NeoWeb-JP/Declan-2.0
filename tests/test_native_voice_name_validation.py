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

    def test_history_has_no_enrolment_ui(self):
        # Speaker enrolment is managed in VoicePipeline, not History.
        timeline = JS.split("  renderTimeline() {", 1)[1].split("  async loadLearnedIntents()", 1)[0]
        self.assertNotIn("Enrol new speaker", timeline)
        self.assertNotIn("Enrol speaker", timeline)
        self.assertNotIn("this.resolveVoice(item.id, 'enrol', trimmed)", timeline)
        self.assertIn("this.resolveVoice(item.id, 'dismiss', null)", timeline)


if __name__ == "__main__":
    unittest.main()
