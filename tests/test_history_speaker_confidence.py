"""Regression coverage for bounded speaker confidence in history metadata."""

import math

import history


def test_history_speaker_match_rejects_nonfinite_confidence():
    for confidence in (math.nan, math.inf, -math.inf):
        result = history.speaker_match({
            "interaction_id": "test-speaker",
            "name": "Example",
            "confidence": confidence,
        })
        assert result == {"name": "Unknown", "interaction_id": "test-speaker"}


def test_history_speaker_match_preserves_finite_confidence():
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
