"""Dispatch stop commands before roast and guest commands."""
from dataclasses import dataclass
from execution_results import Outcome

from declan.turn import roast_guest_dispatch
from declan.music import stop_command_dispatch
from declan.music import stop_result_response


@dataclass(frozen=True)
class DirectDispatchResult:
    reply: str | None
    outcome: Outcome | None
    routine_status: str | None = None

    def __post_init__(self):
        if self.outcome is not None:
            object.__setattr__(self, "outcome", Outcome(self.outcome))


def dispatch(phrase, *, source, origin_device, satellite,
             stop_registry, context_factory, stop_routines,
             stop_everywhere, connection, roast_target,
             respond_to_roast, guest_mode, visitors_present,
             response_guest_mode, roast_respond, assignment_action,
             guest_commands, guest_assignment):
    stop = stop_command_dispatch.dispatch_stop(
        phrase, source=source, origin_device=origin_device,
        satellite=satellite, registry_factory=stop_registry,
        context_factory=context_factory, stop_routines=stop_routines,
        stop_everywhere=stop_everywhere, connection=connection,
    )
    if stop:
        response = stop_result_response.stop_response(stop)
        return DirectDispatchResult(
            reply=response.result.reply, outcome=response.result.outcome,
            routine_status=response.routine_status,
        )
    guest = roast_guest_dispatch.dispatch_roast_or_guest_result(
        phrase, roast_target=roast_target, respond_to_roast=respond_to_roast,
        guest_mode=guest_mode, visitors_present=visitors_present,
        response_guest_mode=response_guest_mode,
        roast_respond=roast_respond, assignment_action=assignment_action,
        guest_commands=guest_commands, guest_assignment=guest_assignment,
        connection=connection,
    )
    if guest is not None:
        return DirectDispatchResult(reply=guest.reply, outcome=guest.outcome)
    return None
