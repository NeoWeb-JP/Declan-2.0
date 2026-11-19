"""Cancel a pending conversational retry and persist the cancellation."""
import sqlite3
from copy import deepcopy
from dataclasses import dataclass, replace
from execution_results import ExecutionResult, Outcome


@dataclass(frozen=True)
class RetryCancellationResult:
    result: ExecutionResult
    session_response: dict
    history_saved: bool = True

    def __post_init__(self):
        if not isinstance(self.result, ExecutionResult) or self.result.outcome is not Outcome.CANCELLED:
            raise ValueError("Retry cancellation requires a cancelled execution result")
        if not isinstance(self.session_response, dict) or not isinstance(self.session_response.get("session_id"), str):
            raise ValueError("Retry cancellation requires a session response")
        if type(self.history_saved) is not bool:
            raise ValueError("History saved must be a boolean")
        object.__setattr__(self, "session_response", deepcopy(self.session_response))

    def to_wire(self):
        reply = deepcopy(self.session_response)
        reply.update(reply=self.result.reply, outcome=self.result.outcome.value,
                     continue_conversation=False)
        if not self.history_saved:
            reply["history_saved"] = False
        return reply


def cancel_retry(message, session_id, *, scope, source, speaker,
                 converse, record, log_error):
    """Compatibility API returning the existing cancellation response mapping."""
    return cancel_retry_result(
        message, session_id, scope=scope, source=source, speaker=speaker,
        converse=converse, record=record, log_error=log_error,
    ).to_wire()


def cancel_retry_result(message, session_id, *, scope, source, speaker,
                        converse, record, log_error):
    """Build and record the cancelled turn without invoking command handlers."""
    reply = converse(message, session_id, "", scope=scope)
    result = RetryCancellationResult(ExecutionResult(reply["reply"], Outcome.CANCELLED), reply)
    try:
        record(reply["session_id"], source, message, "", result.result.outcome.value,
               speaker=speaker if source == "assist" else None)
    except (OSError, sqlite3.Error):
        result = replace(result, history_saved=False)
        log_error("Could not save conversation history.")
    return result
