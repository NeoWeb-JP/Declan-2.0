"""Conversation history persistence boundary for completed assistant turns."""
import sqlite3


def save_turn(reply, *, source, message, outcome, routine_status,
              action_results, phrase_suggestion, speaker, record,
              diagnostic_id, log_error):
    """Record the spoken exchange and preserve existing failure semantics."""
    try:
        record(reply["session_id"], source, message, reply["reply"], outcome,
               routine_status, action_results, phrase_suggestion,
               speaker=speaker if source == "assist" else None,
               diagnostic_id=diagnostic_id())
        if action_results:
            reply["action_results"] = action_results
        return True
    except (OSError, sqlite3.Error):
        log_error("Could not save conversation history.")
        reply["history_saved"] = False
        return False
