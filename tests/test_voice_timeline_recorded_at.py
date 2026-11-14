"""Ensure the HA proxy supplies the recording timestamp for timeline ordering."""
from pathlib import Path
import unittest

VIEW = (Path(__file__).resolve().parents[1] / "custom_components/declan_two/voice_review_view.py").read_text()

class VoiceTimelineTimestampTests(unittest.TestCase):
    def test_both_pending_and_reviewed_return_recorded_at(self):
        self.assertGreaterEqual(VIEW.count('"recorded_at": str(row.get("recorded_at") or "")[:50]'), 2)

if __name__ == "__main__":
    unittest.main()
