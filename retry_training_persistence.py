"""Persistence boundary for successful conversational retry training."""
import sqlite3


def save_retry_training(reply, *, pending_retry, retry_succeeded, message,
                        effective_message, similar, normalize_phrase,
                        teach_phrase, log_error):
    """Learn only a similar, successful rephrasing; tolerate storage failures."""
    if not (pending_retry and retry_succeeded
            and similar(pending_retry["text"], message)
            and normalize_phrase(pending_retry["text"]) != normalize_phrase(effective_message)):
        return False
    try:
        teach_phrase(pending_retry["text"], effective_message, automatic=True)
        reply["learned_from_retry"] = True
        return True
    except (ValueError, OSError, sqlite3.Error):
        log_error("Could not save successful retry training.")
        return False
