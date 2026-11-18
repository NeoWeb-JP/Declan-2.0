"""Roast and guest command dispatch orchestration."""


def dispatch_roast_guest(
    phrase, *, dispatch, roast_target, respond_to_roast, guest_mode,
    visitors_present, response_guest_mode, roast_respond,
    assignment_action, guest_commands, guest_assignment, connection,
):
    return dispatch(
        phrase, roast_target=roast_target, respond_to_roast=respond_to_roast,
        guest_mode=guest_mode, visitors_present=visitors_present,
        response_guest_mode=response_guest_mode, roast_respond=roast_respond,
        assignment_action=assignment_action, guest_commands=guest_commands,
        guest_assignment=guest_assignment, connection=connection,
    )
