"""Validate HTTP conversation message and optional session identifier."""


def message_and_session(body):
    """Preserve the existing 1-1000 character and session length contracts."""
    message = body["message"].strip()
    session_id = body.get("session_id")
    if not 0 < len(message) <= 1000:
        raise ValueError("Message must be 1 to 1,000 characters.")
    if session_id is not None and (not isinstance(session_id, str) or len(session_id) > 64):
        raise ValueError("Invalid session identifier.")
    return message, session_id
