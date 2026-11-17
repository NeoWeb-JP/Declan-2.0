"""Dispatch timer requests unless a routine preview already resolved."""


def dispatch_timer(phrase, *, source, origin_device, satellite, routine_preview,
                   registry_factory, context_factory, matches, handle, opener,
                   guest_mode, decorate):
    """Return a timer dispatch result, or None when preview takes precedence."""
    if routine_preview:
        return None
    registry = registry_factory(matches=matches, handle=handle, opener=opener,
                                guest_mode=guest_mode, decorate=decorate)
    return registry.dispatch(context_factory(
        phrase=phrase, source=source, origin_device=origin_device, satellite=satellite))
