"""Cancel a pending conversational retry and persist the cancellation."""
import sqlite3


def cancel_retry(message, session_id, *, scope, source, speaker,
                 converse, record, log_error):
    """Build and record the cancelled turn without invoking command handlers."""
    reply = converse(message, session_id, "", scope=scope)
    reply.update(outcome="cancelled", continue_conversation=False)
    try:
        record(reply["session_id"], source, message, "", "cancelled",
               speaker=speaker if source == "assist" else None)
    except (OSError, sqlite3.Error):
        reply["history_saved"] = False
        log_error("Could not save conversation history.")
    return reply
