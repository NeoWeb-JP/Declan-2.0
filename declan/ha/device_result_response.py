"""Convert device dispatch results and retain status target context."""
from declan.turn.command_response import CommandResponse


def device_response(device_result):
    """Retain typed execution and the device follow-up target."""
    return CommandResponse(device_result.result, status_target=device_result.status_target)
