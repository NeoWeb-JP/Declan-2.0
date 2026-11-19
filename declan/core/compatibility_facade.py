"""Legacy compatibility conversions delegated from the HTTP entry module."""

def track_routine(name, script, *, r):
    """Compatibility context manager for mapped routine execution."""
    return r.ACTIVE_ROUTINE_REGISTRY.track(name, script)


def stop_pending_routines_result(*, r):
    return r.routine_cancellation.stop_pending_routines_result(
        connection_factory=r.ha_device_connection,
        active_registry=r.ACTIVE_ROUTINE_REGISTRY,
    )



def routine_action_results_typed(steps, *, r):
    """Read validated typed evidence from the mapped routine provider."""
    return r.parse_routine_actions(steps)

def select_routine(phrase, origin, *, r):
    result = r.select_routine_result(phrase, origin)
    return r.RoutineSelection.coerce(result).as_legacy_pair() if result is not None else None

def select_routine_turn(phrase, origin, *, r):
    result = r.select_routine_turn_result(phrase, origin)
    return r.RoutineTurnSelection.coerce(result).as_legacy_pair() if result is not None else None

def _routine_legacy_triple(result, status, *, r):
    """Preserve legacy routine callers while validating discovered script outcomes."""
    return result.reply, result.outcome.value, status

def execute_routine(selection, action_results, *, approved=False, r):
    return r._routine_legacy_triple(*r.execute_routine_result(selection, action_results, approved=approved))
