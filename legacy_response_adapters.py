"""Legacy wire-format adapters with live server dependency resolution."""

def run_custom_routine(name, action_results=None, *, approved=False, parameters=None, *, r):
    """Compatibility API for mapped routine reply/outcome/status triples."""
    return r._routine_legacy_triple(*r.run_custom_routine_result(
        name, action_results, approved=approved, parameters=parameters))


def run_routine(period, *, action_results=None, movie_action=None, movie_room="lounge", movie_app=None, approved=False, *, r):
    """Compatibility API for mapped routine execution."""
    return r._routine_legacy_triple(*r.run_routine_result(
        period, action_results=action_results, movie_action=movie_action,
        movie_room=movie_room, movie_app=movie_app, approved=approved))


def format_routine_result(result, request_id, routine_id, period, movie_action, action_results, *, r):
    """Compatibility API for correlated routine completion replies."""
    return r._routine_legacy_triple(*r.routine_completion_result(
        result, request_id, routine_id, period, movie_action, action_results))


def run_sexy_time(operation, connection, *, approved=False, *, r):
    """Compatibility API for the mapped bedroom routine."""
    return r._routine_legacy_triple(*r.run_sexy_time_result(operation, connection, approved=approved))


def launch_movie_app(connection, remote, app, *, r):
    """Compatibility API for app-launch status and detail strings."""
    return r.launch_movie_app_result(connection, remote, app).as_legacy_pair()


def start_dinner(connection, *, approved=False, *, r):
    """Compatibility API for announcement reply/outcome strings."""
    return r.start_dinner_result(connection, approved=approved).as_legacy_pair()


def guest_assignment(operation, connection, *, r):
    """Compatibility API for guest assignment reply/outcome strings."""
    return r.guest_assignment_result(operation, connection).as_legacy_pair()


def set_switch_as_light(name, desired_state, inventory, connection, *, preview=False, action_results=None, *, r):
    """Compatibility API for marked switch-as-light reply/outcome pairs."""
    result = r.set_switch_as_light_result(name, desired_state, inventory, connection,
                                      preview=preview, action_results=action_results)
    return result.as_legacy_pair() if result is not None else None


def guarded_openai_fallback(message, *, source, exposed_entities=(), *, r):
    """Compatibility API retaining the reply/outcome/action-steps triple."""
    response = r.guarded_openai_fallback_result(message, source=source, exposed_entities=exposed_entities)
    return response.as_legacy_triple() if response is not None else None


def preview_routine(phrase, origin=None, *, r):
    """Compatibility API for read-only preview reply/outcome pairs."""
    return r.preview_routine_result(phrase, origin).as_legacy_pair()

