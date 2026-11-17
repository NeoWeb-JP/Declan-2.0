"""Execute guarded AI fallback after local command handlers have declined."""


def dispatch_fallback(message, *, source, exposed_entities, fallback_handler, action_results):
    """Return a (reply, outcome) pair or None, preserving fallback action steps."""
    fallback = fallback_handler(message, source=source, exposed_entities=exposed_entities)
    if fallback is None:
        return None
    reply, outcome, fallback_steps = fallback
    action_results.extend(fallback_steps)
    return reply, outcome
