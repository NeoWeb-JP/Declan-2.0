"""Typed routine helpers still resolved through the server module (`r=`).

The string-returning twins were retired; these three remain until the `r=`
service-locator is replaced by an explicit dependency container.
"""

def track_routine(name, script, *, r):
    """Context manager tracking a mapped routine while it runs."""
    return r.ACTIVE_ROUTINE_REGISTRY.track(name, script)


def stop_pending_routines_result(*, r):
    return r.routine_cancellation.stop_pending_routines_result(
        connection_factory=r.ha_device_connection,
        active_registry=r.ACTIVE_ROUTINE_REGISTRY,
    )



def routine_action_results_typed(steps, *, r):
    """Read validated typed evidence from the mapped routine provider."""
    return r.parse_routine_actions(steps)
