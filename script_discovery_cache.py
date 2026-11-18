"""Bounded, credential-scoped cache for Home Assistant script discovery."""

from hashlib import sha256
from threading import Lock
from time import monotonic


class ScriptDiscoveryCache:
    """Avoid cross-credential results and stale out-of-order refresh writes."""

    def __init__(self, *, max_entries=32):
        self._lock = Lock()
        self._entries = {}
        self._generation = {}
        self._next_generation = 0
        self._max_entries = max_entries

    @staticmethod
    def key(url, headers):
        # Never retain bearer tokens in cache keys or diagnostic output.
        # Preserve header names and values in the digest so different auth
        # and other request scopes cannot share a result.
        fields = sorted((str(name).casefold(), str(value)) for name, value in headers.items())
        scope = repr((url, fields)).encode("utf-8")
        return sha256(scope).digest()

    def get(self, key, *, seconds):
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None and monotonic() - cached[0] < seconds:
                return cached[1]
            return None

    def begin(self, key):
        with self._lock:
            self._next_generation += 1
            generation = self._next_generation
            self._generation[key] = generation
            # Failed requests do not publish cache entries. Bound their
            # generations as well to avoid accumulating one key per token.
            while len(self._generation) > self._max_entries * 2:
                oldest = next(iter(self._generation))
                self._generation.pop(oldest)
                self._entries.pop(oldest, None)
            return generation

    def publish(self, key, generation, value):
        with self._lock:
            if self._generation.get(key) != generation:
                return False
            self._entries[key] = (monotonic(), value)
            while len(self._entries) > self._max_entries:
                oldest = next(iter(self._entries))
                self._entries.pop(oldest)
                self._generation.pop(oldest, None)
            return True

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._generation.clear()
