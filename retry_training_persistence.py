"""Persistence boundary for successful conversational retry training."""
import sqlite3


def save_retry_training(reply, *, pending_retry, retry_succeeded, message,
                        effective_message, similar, normalize_phrase,
                        teach_phrase, log_error):
    """Learn only a similar, successful rephrasing; tolerate storage failures."""
    original = pending_retry.get("text") if isinstance(pending_retry, dict) else None
    if not (retry_succeeded and isinstance(original, str) and original.strip()
            and len(original) <= 4096
            and isinstance(message, str) and isinstance(effective_message, str)):
        return False
    try:
        if (not similar(original, message)
                or normalize_phrase(original) == normalize_phrase(effective_message)):
            return False
        teach_phrase(original, effective_message, automatic=True)
        reply["learned_from_retry"] = True
        return True
    except (ValueError, TypeError, KeyError, AttributeError, OSError, sqlite3.Error):
        log_error("Could not save successful retry training.")
        return False
