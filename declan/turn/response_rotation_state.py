"""Process-local, injectable state for non-repeating spoken response selection."""

from collections import deque
from random import SystemRandom
from threading import Lock


class ResponseRotationState:
    """Select from eligible lines, avoiding recent repeats when possible."""

    def __init__(self, *, window=3, random=None):
        self.lock = Lock()
        self.recent = {}
        self.window = window
        self.random = random if random is not None else SystemRandom()

    def choose(self, key, lines):
        """Use all lines as a fallback when the recent window exhausts options."""
        choices = tuple(lines)
        if not choices:
            return ""
        with self.lock:
            recent = self.recent.setdefault(key, deque(maxlen=self.window))
            eligible = [line for line in choices if line not in recent]
            chosen = self.random.choice(eligible or choices)
            recent.append(chosen)
            return chosen
