"""Thread-safe cooldown state for mapped Home Assistant routines."""
from threading import Lock
from time import monotonic


class RoutineCooldown:
    def __init__(self, *, clock=monotonic, seconds=30):
        self._clock = clock
        self._seconds = seconds
        self._lock = Lock()
        self._attempts = {}

    def claim(self, key):
        """Atomically reject duplicates within the cooldown and claim a new attempt."""
        with self._lock:
            now = self._clock()
            last = self._attempts.get(key)
            if last is not None and now - last < self._seconds:
                return False
            self._attempts[key] = now
            return True
