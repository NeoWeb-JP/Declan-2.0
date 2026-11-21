"""Injectable state for non-repeating spoken response selection.

With a ``namespace`` the pick is delegated to ``line_freshness`` (FUT-61): used
lines rest for days across restarts and low pools are topped up. Without one
(tests, injected randomness) it keeps the process-local recent window.
"""

from collections import deque
from random import SystemRandom
from threading import Lock


class ResponseRotationState:
    """Select from eligible lines, avoiding recent repeats when possible."""

    def __init__(self, *, window=3, random=None, namespace=None):
        self.namespace = namespace
        self.lock = Lock()
        self.recent = {}
        self.window = window
        self.random = random if random is not None else SystemRandom()

    def choose(self, key, lines, *, topic=None, polite=False):
        """Use all lines as a fallback when the recent window exhausts options."""
        choices = tuple(lines)
        if not choices:
            return ""
        if self.namespace:
            from declan.turn import line_freshness
            parts = key if isinstance(key, tuple) else (key,)
            return line_freshness.pick(":".join((self.namespace, *map(str, parts))), choices,
                                       topic=topic, polite=polite)
        with self.lock:
            recent = self.recent.setdefault(key, deque(maxlen=self.window))
            eligible = [line for line in choices if line not in recent]
            chosen = self.random.choice(eligible or choices)
            recent.append(chosen)
            return chosen
