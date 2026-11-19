"""Plain-string views of typed routine results, for tests that assert wire shapes.

The application only uses the typed ``*_result`` APIs; these helpers exist so
tests can keep asserting the (reply, outcome[, status]) shapes without the app
carrying compatibility twins.
"""
import server


def _triple(result, status):
    return result.reply, result.outcome.value, status


def select_routine(phrase, origin):
    result = server.select_routine_result(phrase, origin)
    return server.RoutineSelection.coerce(result).as_legacy_pair() if result is not None else None


def select_routine_turn(phrase, origin):
    result = server.select_routine_turn_result(phrase, origin)
    return server.RoutineTurnSelection.coerce(result).as_legacy_pair() if result is not None else None


def execute_routine(selection, action_results, *, approved=False):
    return _triple(*server.execute_routine_result(selection, action_results, approved=approved))


def run_custom_routine(name, action_results=None, *, approved=False, parameters=None):
    return _triple(*server.run_custom_routine_result(name, action_results, approved=approved, parameters=parameters))


def run_routine(period, *, action_results=None, movie_action=None, movie_room="lounge", movie_app=None, approved=False):
    return _triple(*server.run_routine_result(
        period, action_results=action_results, movie_action=movie_action,
        movie_room=movie_room, movie_app=movie_app, approved=approved))


def format_routine_result(result, request_id, routine_id, period, movie_action, action_results):
    return _triple(*server.routine_completion_result(result, request_id, routine_id, period, movie_action, action_results))


def set_switch_as_light(name, desired_state, inventory, connection, *, preview=False, action_results=None):
    result = server.set_switch_as_light_result(name, desired_state, inventory, connection,
                                               preview=preview, action_results=action_results)
    return result.as_legacy_pair() if result is not None else None


def preview_routine(phrase, origin=None):
    return server.preview_routine_result(phrase, origin).as_legacy_pair()


def read_ha_inventory(connection):
    return server.read_ha_inventory_result(connection).as_legacy_pair()


def read_music_inventory(connection):
    return server.read_music_inventory_result(connection).as_legacy_pair()


def stop_everywhere_output(connection):
    typed, status = server.stop_everywhere_result(connection)
    return typed.reply, typed.outcome.value, status


def stop_origin_output(connection, satellite, device):
    result, status = server.stop_origin_result(connection, satellite, device)
    return result.reply, result.outcome.value, status
