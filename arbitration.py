"""Choose one satellite for overlapping captures of the same utterance."""

import math
from threading import Lock
from time import monotonic, sleep, time


class CaptureArbiter:
    def __init__(self, window=0.25):
        self.window = window
        self.lock = Lock()
        self.groups = []

    def claim(self, phrase, origin, capture, speaker=None):
        if not origin or not isinstance(capture, dict):
            return True
        values = [capture.get(key) for key in ("ended_at", "duration", "rms")]
        if not all(type(value) in (int, float) and math.isfinite(value) for value in values):
            return True
        ended_at, duration, rms = values
        if not (0.1 <= duration <= 65 and 0 <= rms <= 1 and abs(time() - ended_at) < 120):
            return True
        started_at = ended_at - duration
        now = monotonic()
        candidate = {"origin": origin, "rms": rms}
        with self.lock:
            self.groups = [group for group in self.groups if now - group["created"] < 120][-127:]
            if any(group["phrase"] == phrase and abs(group["ended_at"] - ended_at) < 0.01
                   and abs(group["started_at"] - started_at) < 0.01
                   and origin in {item["origin"] for item in group["candidates"]}
                   for group in self.groups):
                return False
            group = next((group for group in self.groups
                          if group["phrase"] == phrase
                          and origin not in {item["origin"] for item in group["candidates"]}
                          and not (speaker and group["speaker"] and speaker != group["speaker"])
                          and min(ended_at, group["ended_at"]) - max(started_at, group["started_at"]) >= 0.1), None)
            if group is None:
                group = {"phrase": phrase, "speaker": speaker, "created": now,
                         "started_at": started_at, "ended_at": ended_at, "candidates": [], "winner": None}
                self.groups.append(group)
            if speaker and group["speaker"] is None:
                group["speaker"] = speaker
            group["candidates"].append(candidate)
            if group["winner"] is not None:
                return False
            remaining = group["created"] + self.window - now
        if remaining > 0:
            sleep(remaining)
        with self.lock:
            if group["winner"] is None:
                group["winner"] = max(group["candidates"], key=lambda item: item["rms"])
            return group["winner"] is candidate
