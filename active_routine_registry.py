"""Thread-safe registry of currently executing Home Assistant scripts."""
from contextlib import contextmanager
from threading import Lock


class ActiveRoutineRegistry:
    def __init__(self):
        self._lock = Lock()
        self._active = {}

    @contextmanager
    def track(self, name, script):
        with self._lock:
            self._active[name] = script
        try:
            yield
        finally:
            with self._lock:
                if self._active.get(name) == script:
                    self._active.pop(name, None)

    def snapshot(self):
        with self._lock:
            return dict(self._active)
