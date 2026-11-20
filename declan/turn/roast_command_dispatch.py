"""Dispatch a matched roast with the configured guest response policy."""
from declan.core.execution_results import ExecutionResult, Outcome


def respond_to_roast_result(target, *, guest_mode, visitors_present, response_guest_mode, respond):
    """Return the existing (reply, outcome) pair for a matched roast target."""
    mode = response_guest_mode(guest_mode(), visitors_present())
    return ExecutionResult(respond(target, guest=mode != "off"), Outcome.CONFIRMED)
