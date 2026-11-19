"""Ownership of the shared, process-local Music Assistant and Spotify state."""

from threading import Lock


class MusicRuntimeState:
    """Keep music handoffs, token cache and skip throttles in one owner.

    The handoff lock serialises local playback/feedback operations. The Spotify
    lock protects the cached access-token lifecycle independently, so remote
    token requests never hold the household playback lock.
    """

    def __init__(self):
        self.handoff = Lock()
        self.spotify_token_lock = Lock()
        self.spotify_token = None
        self.recent_blacklist_skips = {}
        self._operation_lock = Lock()
        self._operation = 0

    def begin_operation(self):
        """Record a state-changing music command and return its generation.

        A background playback check belongs to the generation current when it
        started. Any later command supersedes it, so a user who says Stop right
        after Play never hears a stale "couldn't confirm" announcement.
        """
        with self._operation_lock:
            self._operation += 1
            return self._operation

    def is_current(self, generation):
        with self._operation_lock:
            return generation == self._operation

    def allow_blacklist_skip(self, entity, now, *, interval=10):
        """Reserve one blacklist skip for an entity while handoff is held.

        Returns false if that entity has already been skipped recently.
        The caller owns the handoff lock, which also protects this dictionary.
        """
        if now < self.recent_blacklist_skips.get(entity, 0):
            return False
        self.recent_blacklist_skips[entity] = now + interval
        return True
