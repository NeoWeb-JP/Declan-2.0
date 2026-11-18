"""Routine registry dispatch boundary with explicit dependency injection."""


def dispatch_routine(
    phrase, *, source, origin_device, satellite, action_results,
    dispatch, registry_factory, context_factory, select, execute,
):
    return dispatch(
        phrase, source=source, origin_device=origin_device,
        satellite=satellite, action_results=action_results,
        registry_factory=registry_factory, context_factory=context_factory,
        select=select, execute=execute,
    )
