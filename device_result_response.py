"""Convert device dispatch results and retain status target context."""


def device_result_response(device_result):
    """Return (reply, outcome, status_target) for a handled device request."""
    reply, outcome = device_result.result.as_legacy_pair()
    return reply, outcome, device_result.status_target
