"""Gate guarded AI fallback behind local command results and HA authorization."""
from execution_results import ExecutionResult


def resolve_fallback_result(message, *, routine_reply, light_result, body,
                            authorization, bridge_token, source, action_results,
                            exposed_entities, dispatch_fallback, fallback_handler):
    """Retain typed fallback results behind the existing eligibility/auth gate."""
    # Keep authorization behind the local-handler eligibility check.
    # This is the typed HTTP path; the legacy pair API remains below.
    if routine_reply is not None or light_result is not None:
        return None
    exposed = exposed_entities(body, authorization, bridge_token)
    result = dispatch_fallback(
        message, source=source, exposed_entities=exposed,
        fallback_handler=fallback_handler, action_results=action_results,
    )
    if result is not None and not isinstance(result, ExecutionResult):
        raise ValueError("Fallback dispatch requires a typed execution result")
    return result


def resolve_fallback(message, *, routine_reply, light_result, body,
                     authorization, bridge_token, source, action_results,
                     exposed_entities, dispatch_fallback, fallback_handler):
    """Return fallback response only when local handlers did not reply.

    Authorization is evaluated only when fallback is eligible, and untrusted
    clients cannot supply HA-exposed entities to the fallback handler.
    """
    if routine_reply is not None or light_result is not None:
        return None
    exposed = exposed_entities(body, authorization, bridge_token)
    return dispatch_fallback(
        message, source=source, exposed_entities=exposed,
        fallback_handler=fallback_handler, action_results=action_results,
    )
