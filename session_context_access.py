"""Session-scoped context lookup under the shared session lock."""


def load_recent_context(*, session_id, scope, sessions, lock, now, idle_seconds, retrieve):
    """Return recent lights, device and information context atomically."""
    with lock:
        return retrieve(
            sessions.get(session_id), scope, now=now, idle_seconds=idle_seconds,
        )


def consume_retry_context(*, session_id, scope, sessions, lock, now, window_seconds, consume):
    """Consume a pending retry while holding the session lock."""
    with lock:
        return consume(
            sessions.get(session_id), scope, now=now, window_seconds=window_seconds,
        )
