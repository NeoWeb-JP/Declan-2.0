"""Bounded conversational retry state, independent of HTTP transport."""
import re
from execution_results import Outcome

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
    if (light_result and outcome == "unresolved" and scope is not None
            and not re.match(r"^(?:preview|dry[ -]run)\b", phrase)
            and any(step.get("detail") == "unresolved" for step in action_results)):
        session["failed_light_phrase"] = {
            "text": message, "scope": scope, "actions": actions,
        }
    needs_retry = reply["reply"] == unmatched_reply
    reply["continue_conversation"] = needs_retry
    reply["follow_up_timeout"] = 10 if needs_retry else 0
    if needs_retry and scope is not None:
        session["pending_retry"] = {"text": message, "scope": scope, "at": now}
    return outcome in SUCCESS_OUTCOMES or outcome is None and not needs_retry
