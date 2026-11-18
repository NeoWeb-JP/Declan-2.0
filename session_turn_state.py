"""Bounded conversational retry state, independent of HTTP transport."""
import re
from execution_results import Outcome, parse_outcome
from action_evidence_buffer import evidence_lighting_reason
from lighting_action_evidence import LightingActionReason
from context_numeric_validation import finite_number
from retry_phrase_validation import valid_retry_phrase

SUCCESS_OUTCOMES = frozenset({
    Outcome.CONFIRMED, Outcome.REPORTED_SUCCESS, Outcome.EXECUTION_COMPLETED,
    Outcome.TIMER_SET, Outcome.TIMER_ADJUSTED, Outcome.TIMER_CANCELLED, Outcome.TIMER_STOPPED,
})


def update_turn(session, reply, *, message, phrase, outcome, scope,
                status_target, information_context, light_result,
                action_results, actions, unmatched_reply, now):
    """Record contextual state and schedule a voice correction retry when needed."""
    session["last"] = message
    session["device_status_target"] = status_target
    session["device_status_scope"] = scope
    session["information_context"] = information_context
    session["information_scope"] = scope
    session.pop("failed_light_phrase", None)
    decision_outcome = parse_outcome(outcome)
    if (light_result and decision_outcome is Outcome.UNRESOLVED and scope is not None
            and not re.match(r"^(?:preview|dry[ -]run)\b", phrase)
            and any(evidence_lighting_reason(step) is LightingActionReason.UNRESOLVED for step in action_results)):
        session["failed_light_phrase"] = {
            "text": message, "scope": scope, "actions": actions,
        }
    needs_retry = (reply["reply"] == unmatched_reply and scope is not None
                   and valid_retry_phrase(message) and finite_number(now))
    # Never advertise a listening follow-up without a usable pending retry.
    reply["continue_conversation"] = needs_retry
    reply["follow_up_timeout"] = 10 if needs_retry else 0
    session.pop("pending_retry", None)
    if needs_retry:
        session["pending_retry"] = {"text": message, "scope": scope, "at": now}
    return decision_outcome in SUCCESS_OUTCOMES or outcome is None and not needs_retry
