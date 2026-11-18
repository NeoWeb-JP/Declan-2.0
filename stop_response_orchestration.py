"""Stop-command dispatch and typed response adaptation."""


def dispatch_stop_response(
    phrase, *, source, origin_device, satellite,
    dispatch, registry_factory, context_factory,
    stop_routines, stop_everywhere, connection, adapt,
):
    result = dispatch(
        phrase, source=source, origin_device=origin_device,
        satellite=satellite, registry_factory=registry_factory,
        context_factory=context_factory, stop_routines=stop_routines,
        stop_everywhere=stop_everywhere, connection=connection,
    )
    return adapt(result) if result else None
