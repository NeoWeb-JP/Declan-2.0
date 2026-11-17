"""Pure request-finalisation helpers for HTTP turn handling."""
from execution_results import Outcome, parse_outcome


def lighting_phrase_suggestion(previous, *, light_result, outcome, actions,
                               scope, message, now):
    """Return an earlier unresolved lighting phrase for user-review training."""
    failed_phrase = previous.get("failed_light_phrase") if previous else None
    if (light_result and parse_outcome(outcome) is Outcome.CONFIRMED and actions and scope is not None
            and failed_phrase and failed_phrase["scope"] == scope
            and now - previous["at"] <= 30
            and actions & failed_phrase["actions"]
            and failed_phrase["text"].casefold() != message.casefold()):
        return failed_phrase["text"]
    return None


def apply_outcome_metadata(reply, *, outcome, routine_status):
    """Attach result metadata without modifying the spoken response."""
    if outcome:
        reply["outcome"] = outcome.value if isinstance(outcome, Outcome) else outcome
    if routine_status:
        reply["routine_status"] = routine_status
    return reply
