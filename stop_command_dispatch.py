"""Dispatch stop commands before lower-priority command handlers."""


def dispatch_stop(phrase, *, source, origin_device, satellite, registry_factory,
                  context_factory, stop_routines, stop_everywhere, connection):
    """Return the stop registry dispatch result without changing precedence."""
    registry = registry_factory(stop_routines=stop_routines,
                                stop_everywhere=stop_everywhere,
                                connection=connection)
    return registry.dispatch(context_factory(
        phrase=phrase, source=source, origin_device=origin_device, satellite=satellite))
