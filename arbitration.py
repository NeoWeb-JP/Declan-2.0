"""Claim overlapping copies once, independently of transcription arrival latency."""
import math
import re
from threading import Lock
from time import monotonic, time


def command_key(phrase):
    # Only explicit harmless variants. Fuzzy matching can merge opposite actions.
    phrase = " ".join(phrase.casefold().strip(" .?!").split())
    return re.sub(r"^(turn (?:on|off) (?:the )?)lights(?=$| in )", r"\1light", phrase)


class CaptureArbiter:
    def __init__(self, window=None, retention=120):
        # Keep window accepted for old callers; no sleep is imposed.
        self.retention = retention
        self.lock = Lock()
        self.groups = []

    def claim(self, phrase, origin, capture, speaker=None):
        if not origin or not isinstance(capture, dict):
            return True
        values = [capture.get(key) for key in ("ended_at", "duration", "rms")]
        if not all(type(value) in (int, float) and math.isfinite(value) for value in values):
            return True
        ended_at, duration, rms = values
        if not (0.1 <= duration <= 65 and 0 <= rms <= 1 and abs(time() - ended_at) < self.retention):
            return True
        started_at = ended_at - duration
        now = monotonic()
        phrase = command_key(phrase)
        with self.lock:
            self.groups = [group for group in self.groups if now - group["created"] < self.retention]
            for group in self.groups:
                if phrase != group["phrase"] or (speaker and group["speaker"] and speaker != group["speaker"]):
                    continue
                exact = abs(group["ended_at"] - ended_at) < 0.01 and abs(group["started_at"] - started_at) < 0.01
                overlap = min(ended_at, group["ended_at"]) - max(started_at, group["started_at"])
                same = overlap >= 0.8 * min(duration, group["duration"]) and abs(ended_at - group["ended_at"]) <= 1
                if (origin == group["origin"] and exact) or (origin != group["origin"] and same):
                    return False
            # Never evict a live claim under load and accidentally execute it twice.
            if len(self.groups) >= 4096:
                return False
            self.groups.append(dict(phrase=phrase, origin=origin, speaker=speaker, created=now,
                                    started_at=started_at, ended_at=ended_at, duration=duration))
            return True
