"""Build and persist sensitive action confirmation responses."""
import sqlite3


CONFIRMATION_REPLIES = {
    "prompt": "Please confirm or cancel this action within 30 seconds.",
    "cancelled": "Cancelled. Nothing has been run.",
    "denied": "I can't identify the originating satellite for that action.",
}


def confirmation_response(decision, session_id, *, source, message, speaker,
                          record, diagnostic_id, log_error):
    """Return a response for a blocking confirmation decision, or None."""
    if decision not in CONFIRMATION_REPLIES:
        return None
    response = CONFIRMATION_REPLIES[decision]
    result = {"reply": response, "session_id": session_id,
              "outcome": "confirmation_" + decision,
              "continue_conversation": decision == "prompt"}
    try:
        record(session_id, source, message, response, result["outcome"],
               speaker=speaker, diagnostic_id=diagnostic_id())
    except (OSError, sqlite3.Error):
        result["history_saved"] = False
        log_error("Could not save conversation history.")
    return result
