"""Issue 12: conversation context must not cross physical satellite origins."""
from pathlib import Path
import ast
import unittest

class SatelliteContextTests(unittest.TestCase):
    def test_no_cross_room_context_and_high_confidence(self):
        source=Path(__file__).resolve().parents[1].joinpath("server.py").read_text()
        ast.parse(source)
        self.assertNotIn("SPEAKER_CONTEXTS", source)
        self.assertNotIn("speaker_scope", source)
        self.assertIn('speaker["confidence"] >= 0.85', source)
        # Scope checks live in the extracted session context retrieval module.
        context_source = Path(__file__).resolve().parents[1].joinpath(
            "session_context_retrieval.py").read_text()
        ast.parse(context_source)
        self.assertIn('previous.get("information_scope") == scope', context_source)
        self.assertIn('previous.get("lighting_scope") == scope', context_source)
        self.assertIn('previous.get("device_status_scope") == scope', context_source)
        self.assertIn("session_context_retrieval.recent_context(", source)
        self.assertIn('IDLE_SECONDS = 300', source)

if __name__=="__main__":
    unittest.main()
