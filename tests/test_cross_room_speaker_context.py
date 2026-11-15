"""Cross-room context is only shared when VoicePipeline identified a speaker."""
from pathlib import Path
import ast
import unittest
class CrossRoomContextTests(unittest.TestCase):
    def test_recognised_only(self):
        source=Path(__file__).resolve().parents[1].joinpath("server.py").read_text()
        ast.parse(source)
        self.assertIn('speaker_scope = None',source)
        self.assertIn('if speaker_name and speaker_name.strip():',source)
        self.assertIn('speaker_scope = ("assist", "speaker", speaker_name.strip().casefold())',source)
        self.assertIn('if speaker_scope is not None:',source)
        self.assertIn('SPEAKER_CONTEXTS.get(speaker_scope)',source)
        self.assertIn('monotonic() - shared["at"] < IDLE_SECONDS',source)
        self.assertIn('if len(SPEAKER_CONTEXTS) > 100:',source)
if __name__=="__main__": unittest.main()
