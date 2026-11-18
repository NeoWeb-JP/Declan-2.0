"""Orchestration for the final lighting, fallback and persona dispatch stages."""


def dispatch_lighting(
    phrase, *, source, origin_device, satellite, dispatch,
    registry_factory, context_factory, matches, parse_light_command,
    handle_light_request, action_results, last_lights, scope,
    dispatch_lighting_command, confirmed_lighting_context,
):
    return dispatch(
        phrase, source=source, origin_device=origin_device,
        satellite=satellite, registry_factory=registry_factory,
        context_factory=context_factory, matches=matches,
        parse_light_command=parse_light_command,
        handle_light_request=handle_light_request,
        action_results=action_results, last_lights=last_lights,
        scope=scope, dispatch_lighting=dispatch_lighting_command,
        confirmed_lighting_context=confirmed_lighting_context,
    )


def resolve_fallback(
    message, *, routine_reply, light_result, body, authorization,
    bridge_token, source, action_results, resolve, exposed_entities,
    dispatch_fallback, fallback_handler,
):
    return resolve(
        message, routine_reply=routine_reply, light_result=light_result,
        body=body, authorization=authorization, bridge_token=bridge_token,
        source=source, action_results=action_results,
        exposed_entities=exposed_entities, dispatch_fallback=dispatch_fallback,
        fallback_handler=fallback_handler,
    )


def resolve_persona(*, resolve, guest_mode, visitors_present, personality):
    return resolve(guest_mode, visitors_present, personality)
