"""Convert a dispatched stop command into its legacy reply and status."""


def stop_result_response(stop_result):
    """Return (reply, outcome, routine_status) for a dispatched stop result."""
    reply, outcome = stop_result.result.as_legacy_pair()
    return reply, outcome, stop_result.routine_status
