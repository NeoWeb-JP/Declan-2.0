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

    def allow_blacklist_skip(self, entity, now, *, interval=10):
        """Reserve one blacklist skip for an entity while handoff is held.

        Returns false if that entity has already been skipped recently.
        The caller owns the handoff lock, which also protects this dictionary.
        """
        if now < self.recent_blacklist_skips.get(entity, 0):
            return False
        self.recent_blacklist_skips[entity] = now + interval
        return True
