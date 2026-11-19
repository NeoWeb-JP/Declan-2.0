"""Conversation preflight dependency boundary.

Keep confirmation, retry and speaker context decisions in turn_preflight.
This module only binds the current session store to that implementation.
"""

import turn_preflight


def resolve(handler, body, *, session_store, **dependencies):
    """Forward preflight with live session state and its existing lock."""
    return turn_preflight.resolve(
        handler, body, sessions=session_store.sessions,
        lock=session_store.lock, **dependencies,
    )
