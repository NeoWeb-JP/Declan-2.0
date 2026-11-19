"""History regression tests executed by unittest discovery."""

import tempfile
import unittest
from pathlib import Path
import math

import history


class HistoryRegressionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.old_database = history.DATABASE
        self.addCleanup(setattr, history, "DATABASE", self.old_database)
        history.DATABASE = Path(self.directory.name) / "history.sqlite3"

    def test_history_speaker_match_rejects_nonfinite_confidence(self):
        for confidence in (math.nan, math.inf, -math.inf):
            result = history.speaker_match({
                "interaction_id": "test-speaker",
                "name": "Example",
                "confidence": confidence,
            })
            assert result == {"name": "Unknown", "interaction_id": "test-speaker"}


    def test_history_speaker_match_preserves_finite_confidence(self):
        matched = history.speaker_match({
            "interaction_id": "test-speaker",
            "name": "Example",
            "confidence": 0.9,
        })
        assert matched == {
            "name": "Example", "interaction_id": "test-speaker", "confidence": 0.9,
        }
        candidate = history.speaker_match({"name": "Example", "confidence": 0.5})
        assert candidate == {"name": "Unknown", "candidate": "Example", "confidence": 0.5}

