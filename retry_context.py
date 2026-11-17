"""Bounded, origin-scoped retry context for conversational corrections."""


def consume_pending_retry(session, scope, *, now, window_seconds):
    """Consume the pending retry exactly once and reject expired or foreign scopes."""
    pending = session.pop("pending_retry", None) if session else None
    if pending and (pending["scope"] != scope or scope is None
                    or now - pending["at"] > window_seconds):
        return None
    return pending
