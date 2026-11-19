"""Build and dispatch a Home Assistant routine command request."""


def dispatch_routine(phrase, *, source, origin_device, satellite, action_results,
                     registry_factory, context_factory, select, execute):
    """Use the preferred origin for registry selection, preserving raw context."""
    registry = registry_factory(
        select=select, execute=execute, action_results=action_results,
        origin=origin_device or satellite,
    )
    context = context_factory(
        phrase=phrase, source=source, origin_device=origin_device,
        satellite=satellite,
    )
    return registry.dispatch(context)
