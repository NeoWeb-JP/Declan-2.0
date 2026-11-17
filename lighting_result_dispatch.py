"""Coordinate lighting command dispatch, reply and confirmed lighting context."""


def dispatch_lighting_result(phrase, *, source, origin_device, satellite,
                             registry_factory, context_factory, matches,
                             parse_light_command, handle_light_request,
                             action_results, last_lights, scope,
                             dispatch_lighting, confirmed_lighting_context):
    """Return (reply, outcome, lighting_context), or None when unhandled."""
    dispatched = dispatch_lighting(
        phrase, source=source, origin_device=origin_device, satellite=satellite,
        registry_factory=registry_factory, context_factory=context_factory,
        matches=matches, parse_light_command=parse_light_command,
        handle_light_request=handle_light_request,
        action_results=action_results, last_lights=last_lights,
    )
    if dispatched is None:
        return None
    result = dispatched.result.as_legacy_pair()
    if not result:
        return None
    reply, outcome = result
    context = confirmed_lighting_context(phrase, outcome, scope, action_results)
    return reply, outcome, context
