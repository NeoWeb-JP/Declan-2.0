"""Session-scoped context lookup under the shared session lock."""


def _existing_session(sessions, session_id):
    """Untrusted request IDs must not be used as mapping keys without validation."""
    if not isinstance(session_id, str) or not session_id or len(session_id) > 256:
        return None
    state = sessions.get(session_id)
    return state if isinstance(state, dict) else None


def load_recent_context(*, session_id, scope, sessions, lock, now, idle_seconds, retrieve):
    """Return recent lights, device and information context atomically."""
    with lock:
        return retrieve(
            _existing_session(sessions, session_id), scope, now=now, idle_seconds=idle_seconds,
        )


def consume_retry_context(*, session_id, scope, sessions, lock, now, window_seconds, consume):
    """Consume a pending retry while holding the session lock."""
    with lock:
        return consume(
            _existing_session(sessions, session_id), scope, now=now, window_seconds=window_seconds,
        )
