"""Synchronized owner for playlist curation and discovery refresh status."""

from threading import RLock


class PlaylistRefreshState:
    """Keep the curation mutex and single refresh slot in one instance."""

    def __init__(self):
        self.lock = RLock()
        self._refresh = {"running": False, "category": None,
                         "error": None, "completed": None}

    def snapshot(self):
        with self.lock:
            return dict(self._refresh)

    def claim(self, category):
        """Atomically reserve the one background discovery worker."""
        with self.lock:
            if self._refresh["running"]:
                return False
            self._refresh.update(running=True, category=category, error=None, completed=None)
            return True

    def failure(self, message):
        with self.lock:
            self._refresh["error"] = message

    def finish(self, completed):
        with self.lock:
            self._refresh["running"] = False
            self._refresh["completed"] = completed
