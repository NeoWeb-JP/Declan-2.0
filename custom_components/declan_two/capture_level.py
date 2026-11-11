"""Measure capture loudness without retaining audio after transcription."""

from array import array
from math import sqrt
import sys
from time import time


class CaptureLevel:
    def __init__(self):
        self.count = 0
        self.squares = 0
        self.pending = b""
        self.ended_at = None

    def add(self, data):
        data = self.pending + data
        self.pending = data[len(data) - len(data) % 2:]
        samples = array("h")
        samples.frombytes(data[:len(data) - len(data) % 2])
        if sys.byteorder != "little":
            samples.byteswap()
        self.count += len(samples)
        self.squares += sum(value * value for value in samples)

    def finish(self):
        self.ended_at = time()

    def snapshot(self):
        if not self.count or self.ended_at is None:
            return None
        return {"ended_at": self.ended_at, "duration": self.count / 16000,
                "rms": sqrt(self.squares / self.count) / 32768}
