"""Validate HTTP conversation message and optional session identifier."""


def message_and_session(body):
    """Validate JSON payload types before normalising text or session IDs."""
    if not isinstance(body, dict):
        raise ValueError("Expected a JSON object.")
    message = body.get("message")
    if not isinstance(message, str):
        raise ValueError("Message must be a string.")
    message = message.strip()
    if not 0 < len(message) <= 1000:
        raise ValueError("Message must be 1 to 1,000 characters.")
    session_id = body.get("session_id")
    if session_id is not None and (not isinstance(session_id, str) or not session_id or len(session_id) > 64):
        raise ValueError("Invalid session identifier.")
    return message, session_id
