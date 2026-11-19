"""Convert device dispatch results and retain status target context."""
from declan.turn.command_response import CommandResponse


def device_response(device_result):
    """Retain typed execution and the device follow-up target."""
    return CommandResponse(device_result.result, status_target=device_result.status_target)


def device_result_response(device_result):
    """Return (reply, outcome, status_target) for a handled device request."""
    reply, outcome = device_result.result.as_legacy_pair()
    return reply, outcome, device_result.status_target
