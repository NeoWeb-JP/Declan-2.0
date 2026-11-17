"""Build and persist sensitive action confirmation responses."""
import sqlite3
from execution_results import Outcome
from confirmation_results import ConfirmationDecision, ConfirmationReplyResult


CONFIRMATION_REPLIES = {
    ConfirmationDecision.PROMPT: "Please confirm or cancel this action within 30 seconds.",
    ConfirmationDecision.CANCELLED: "Cancelled. Nothing has been run.",
    ConfirmationDecision.DENIED: "I can't identify the originating satellite for that action.",
}


def confirmation_reply_result(decision) -> ConfirmationReplyResult | None:
    """Interpret legacy decisions once, retaining typed response metadata."""
    if not isinstance(decision, str):
        return None
    try:
        decision = ConfirmationDecision(decision)
    except ValueError:
        return None
    outcomes = {ConfirmationDecision.PROMPT: Outcome.CONFIRMATION_PROMPT,
                ConfirmationDecision.CANCELLED: Outcome.CONFIRMATION_CANCELLED,
                ConfirmationDecision.DENIED: Outcome.CONFIRMATION_DENIED}
    if decision not in outcomes:
        return None
    return ConfirmationReplyResult(CONFIRMATION_REPLIES[decision], outcomes[decision],
                                   decision is ConfirmationDecision.PROMPT)


def confirmation_response(decision, session_id, *, source, message, speaker,
                          record, diagnostic_id, log_error):
    """Return a response for a blocking confirmation decision, or None."""
    response = confirmation_reply_result(decision)
    if response is None:
        return None
    result = response.to_wire(session_id)
    try:
        record(session_id, source, message, response.reply, response.outcome.value,
               speaker=speaker, diagnostic_id=diagnostic_id())
    except (OSError, sqlite3.Error):
        result["history_saved"] = False
        log_error("Could not save conversation history.")
    return result
