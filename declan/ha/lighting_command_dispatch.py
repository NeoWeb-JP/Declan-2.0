"""Dispatch lighting requests after higher-priority local commands."""


def dispatch_lighting(phrase, *, source, origin_device, satellite,
                      registry_factory, context_factory, matches,
                      parse_light_command, handle_light_request,
                      action_results, last_lights):
    """Return the lighting registry dispatch result without altering response handling."""
    registry = registry_factory(
        matches=matches, parse_light_command=parse_light_command,
        handle_light_request=handle_light_request, action_results=action_results,
        last_lights=last_lights, origin_device=origin_device,
    )
    return registry.dispatch(context_factory(
        phrase=phrase, source=source, origin_device=origin_device, satellite=satellite,
    ))
