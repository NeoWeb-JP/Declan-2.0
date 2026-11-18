"""Owned, bounded and thread-safe logging feed storage and handler lifecycle."""

from collections import deque
from threading import RLock


class LogFeedState:
    """Own a bounded log queue and its single root logger handler."""

    def __init__(self, *, capacity=500):
        self.lock = RLock()
        self.entries = deque(maxlen=capacity)
        self.handler = None

    def append(self, item):
        with self.lock:
            self.entries.append(item)

    def snapshot(self, *, threshold, limit):
        with self.lock:
            entries = [item.copy() for item in reversed(self.entries)
                       if item["levelno"] >= threshold]
        for item in entries:
            item.pop("levelno", None)
        return entries[:limit]

    def install(self, root, handler_factory):
        with self.lock:
            if self.handler is None:
                self.handler = handler_factory()
            if self.handler not in root.handlers:
                root.addHandler(self.handler)
