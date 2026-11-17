"""Convert a dispatched stop command into its legacy reply and status."""
from command_response import CommandResponse


def stop_response(stop_result):
    """Retain the typed execution result and optional routine status."""
    return CommandResponse(stop_result.result, routine_status=stop_result.routine_status)


def stop_result_response(stop_result):
    """Return (reply, outcome, routine_status) for a dispatched stop result."""
    reply, outcome = stop_result.result.as_legacy_pair()
    return reply, outcome, stop_result.routine_status
