"""Bounded conversational retry state, independent of HTTP transport."""
import re

SUCCESS_OUTCOMES = frozenset({
    "confirmed", "reported_success", "execution_completed",
    "timer_set", "timer_adjusted", "timer_cancelled", "timer_stopped",
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
