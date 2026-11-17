"""Dispatch roast and guest assignment commands in existing priority order."""
from execution_results import ExecutionResult


def dispatch_roast_or_guest(phrase, *, roast_target, respond_to_roast,
                            guest_mode, visitors_present, response_guest_mode,
                            roast_respond, assignment_action, guest_commands,
                            guest_assignment, connection):
    """Return (reply, outcome), or None if neither command matches."""
    target = roast_target(phrase)
    if target is not None:
        return respond_to_roast(
            target, guest_mode=guest_mode,
            visitors_present=visitors_present,
            response_guest_mode=response_guest_mode,
            respond=roast_respond,
        )
    action = assignment_action(phrase, guest_commands)
    if action is not None:
        result = guest_assignment(action, connection())
        return result.as_legacy_pair() if isinstance(result, ExecutionResult) else result
    return None
