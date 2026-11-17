"""Gate guarded AI fallback behind local command results and HA authorization."""


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
