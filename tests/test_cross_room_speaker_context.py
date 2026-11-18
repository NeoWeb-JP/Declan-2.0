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
        capture_source = Path(__file__).resolve().parents[1].joinpath(
            "assist_capture_http.py").read_text()
        ast.parse(capture_source)
        turn_source = Path(__file__).resolve().parents[1].joinpath("turn_initialization.py").read_text()
        ast.parse(turn_source)
        self.assertIn("turn_initialization.prepare(", source)
        self.assertIn("assist_capture_http.suppress_duplicate(", turn_source)
        self.assertIn('speaker["confidence"] >= 0.85', capture_source)
        # Scope checks live in the extracted session context retrieval module.
        context_source = Path(__file__).resolve().parents[1].joinpath(
            "session_context_retrieval.py").read_text()
        ast.parse(context_source)
        for field in ("information_scope", "lighting_scope", "device_status_scope"):
            self.assertIn(f'valid_retry_scope(previous.get("{field}"))', context_source)
            self.assertIn(f'previous["{field}"] == scope', context_source)
        access_source = Path(__file__).resolve().parents[1].joinpath(
            "session_context_access.py").read_text()
        ast.parse(access_source)
        self.assertIn("session_context_access.load_recent_context(", turn_source)
        self.assertIn("retrieve=session_context_retrieval.recent_context", source)
        self.assertIn("with lock:", access_source)
        self.assertIn('IDLE_SECONDS = 300', source)

if __name__=="__main__":
    unittest.main()
