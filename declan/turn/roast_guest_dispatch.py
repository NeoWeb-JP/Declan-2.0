"""Dispatch roast and guest assignment commands in existing priority order."""
from declan.core.execution_results import ExecutionResult


def dispatch_roast_or_guest_result(phrase, *, roast_target, respond_to_roast,
                                   guest_mode, visitors_present, response_guest_mode,
                                   roast_respond, assignment_action, guest_commands,
                                   guest_assignment, connection):
    """Keep typed outcomes while retaining roast-before-guest ownership."""
    target = roast_target(phrase)
    if target is not None:
        result = respond_to_roast(
            target, guest_mode=guest_mode, visitors_present=visitors_present,
            response_guest_mode=response_guest_mode, respond=roast_respond,
        )
    else:
        action = assignment_action(phrase, guest_commands)
        if action is None:
            return None
        result = guest_assignment(action, connection())
    if isinstance(result, ExecutionResult):
        return result
    if not isinstance(result, (tuple, list)) or len(result) != 2:
        raise ValueError("Roast/guest provider requires a typed result or legacy pair")
    return ExecutionResult(*result)
