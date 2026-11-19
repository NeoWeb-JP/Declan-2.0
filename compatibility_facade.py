"""Legacy compatibility conversions delegated from the HTTP entry module."""

def track_routine(name, script, *, r):
    """Compatibility context manager for mapped routine execution."""
    return r.ACTIVE_ROUTINE_REGISTRY.track(name, script)

def stop_pending_routines(*, r):
    """Compatibility API for mapped routine cancellation."""
    return r._routine_legacy_triple(*r.stop_pending_routines_result())

def stop_pending_routines_result(*, r):
    return r.routine_cancellation.stop_pending_routines_result(
        connection_factory=r.ha_device_connection,
        active_registry=r.ACTIVE_ROUTINE_REGISTRY,
    )

def home_assistant_status(*, r):
    """Compatibility API returning the original connection status string."""
    return r.home_assistant_status_result().status.value

def routine_action_results(steps, *, r):
    """Compatibility API retaining bounded plain-string evidence mappings."""
    return [step.to_wire() for step in r.routine_action_results_typed(steps)]

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

def chained_outcome(routine, lighting, *, r):
    """Compatibility API for plain outcome strings."""
    return r.chained_outcome_result(routine, lighting).value

def search_media(phrase, *, r):
    """Compatibility API retaining plain reply/outcome pairs."""
    result = r.search_media_result(phrase)
    return result.as_legacy_pair() if result is not None else None

def traced_transcribe(*args, r, **kwargs):
    """Compatibility API retaining the transcript string and timing stage."""
    return r.traced_transcribe_result(*args, **kwargs).text
