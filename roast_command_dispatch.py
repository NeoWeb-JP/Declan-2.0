"""Dispatch a matched roast with the configured guest response policy."""
from execution_results import ExecutionResult, Outcome


def respond_to_roast(target, *, guest_mode, visitors_present, response_guest_mode, respond):
    """Compatibility API retaining plain reply/outcome pairs."""
    return respond_to_roast_result(
        target, guest_mode=guest_mode, visitors_present=visitors_present,
        response_guest_mode=response_guest_mode, respond=respond,
    ).as_legacy_pair()


def respond_to_roast_result(target, *, guest_mode, visitors_present, response_guest_mode, respond):
    """Return the existing (reply, outcome) pair for a matched roast target."""
    mode = response_guest_mode(guest_mode(), visitors_present())
    return ExecutionResult(respond(target, guest=mode != "off"), Outcome.CONFIRMED)
