"""Convert a dispatched stop command into its legacy reply and status."""
from declan.turn.command_response import CommandResponse


def stop_response(stop_result):
    """Retain the typed execution result and optional routine status."""
    return CommandResponse(stop_result.result, routine_status=stop_result.routine_status)
