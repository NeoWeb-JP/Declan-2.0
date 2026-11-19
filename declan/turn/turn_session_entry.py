"""Conversation turn initialization and session context boundary."""

from declan.turn import turn_initialization


def prepare(handler, body, *, message, session_id, arbiter, normalize,
            new_session_id, session_store, now, idle_seconds, retrieve):
    """Preserve session locking, id generation, and recent-context retrieval."""
    return turn_initialization.prepare(
        handler, body, message=message, session_id=session_id,
        arbiter=arbiter, normalize=normalize,
        new_session_id=new_session_id,
        sessions=session_store.sessions, lock=session_store.lock,
        now=now, idle_seconds=idle_seconds, retrieve=retrieve,
    )
