"""Thread-safe registry of currently executing Home Assistant scripts."""
from contextlib import contextmanager
from threading import Lock


class ActiveRoutineRegistry:
    def __init__(self):
        self._lock = Lock()
        self._active = {}

    @contextmanager
    def track(self, name, script):
        # An identity marker distinguishes two overlapping runs of the same script.
        registration = object()
        with self._lock:
            self._active[name] = (script, registration)
        try:
            yield
        finally:
            with self._lock:
                active = self._active.get(name)
                if active is not None and active[1] is registration:
                    self._active.pop(name, None)

    def snapshot(self):
        with self._lock:
            return {name: script for name, (script, _) in self._active.items()}
