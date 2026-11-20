"""VOI-12: how often Declan did not understand, and how confident speaker ID is.

Read-only summary of retained History. "Not understood" means the saved reply
is the unmatched rephrase prompt, so it counts both local-parser misses and
turns the AI fallback declined. Only spoken or typed requests count; duplicate
Assist captures and internal sources are ignored.
"""
import json
import math
from collections import Counter
from statistics import median
from time import time

from declan.core import history

REQUEST_SOURCES = frozenset({"assist", "browser_voice", "browser_keyboard", "ha_sentence"})
WEEK = 7 * 24 * 60 * 60
TOP_PHRASES = 10


def _confidence(encoded):
    try:
        match = json.loads(encoded) if encoded else None
    except (TypeError, ValueError):
        return None
    value = match.get("confidence") if isinstance(match, dict) else None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    number = float(value)
    return number if math.isfinite(number) and 0 <= number <= 1 else None


def summary(*, unmatched_reply, speaker_threshold, now=None, weeks=4):
    """Weekly not-understood rate, top missed phrases and speaker confidence."""
    if type(weeks) is not int or not 1 <= weeks <= 5:
        raise ValueError("Weeks must be between 1 and 5.")
    now = time() if now is None else now
    start = max(now - weeks * WEEK, now - history.retention_seconds())
    counts = [[0, 0] for _ in range(weeks)]  # [turns, not understood] per week
    missed: Counter[str] = Counter()
    confidences: list[float] = []
    with history.database() as connection:
        rows = connection.execute(
            "SELECT created_at, source, message, reply, outcome, speaker_match FROM turns "
            "WHERE typeof(created_at) IN ('integer', 'real') AND created_at BETWEEN ? AND ?",
            (start, now),
        ).fetchall()
        learned = dict(connection.execute("SELECT phrase, target FROM learned_intents"))
    for created_at, source, message, reply, outcome, speaker_match in rows:
        if source not in REQUEST_SOURCES or outcome in {"duplicate", "ignored"} or not isinstance(message, str):
            continue
        index = int((now - created_at) // WEEK)
        if not 0 <= index < weeks:
            continue
        counts[index][0] += 1
        if reply == unmatched_reply:
            counts[index][1] += 1
            phrase = history.normalize_phrase(message)
            if 0 < len(phrase) <= 120:
                missed[phrase] += 1
        if source == "assist" and index == 0:
            value = _confidence(speaker_match)
            if value is not None:
                confidences.append(value)
    buckets = [{"turns": turns, "not_understood": misses,
                "rate": round(misses / turns, 4) if turns else None}
               for turns, misses in counts]
    confidences.sort()
    recognised = sum(1 for value in confidences if value >= speaker_threshold)
    return {
        "weeks": buckets,  # index 0 is the last seven days
        "top_not_understood": [
            {"phrase": phrase, "count": count, "learned": phrase in learned}
            for phrase, count in missed.most_common(TOP_PHRASES)
        ],
        "speaker": {
            "threshold": speaker_threshold,
            "samples": len(confidences),
            "median_confidence": round(median(confidences), 4) if confidences else None,
            "highest_confidence": round(confidences[-1], 4) if confidences else None,
            "recognised_share": round(recognised / len(confidences), 4) if confidences else None,
        },
    }
