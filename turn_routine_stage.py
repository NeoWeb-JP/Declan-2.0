"""Select a routine and execute its chained follow-on actions."""
from dataclasses import dataclass
from execution_results import Outcome

import routine_follow_on_dispatch
import routine_registry_dispatch


@dataclass(frozen=True)
class RoutineStageResult:
    reply: str | None
    outcome: Outcome | None
    routine_status: str | None
    routine_turn: object
    lighting_context: object
    routine_voice_result: object

    def __post_init__(self):
        if self.outcome is not None:
            object.__setattr__(self, "outcome", Outcome(self.outcome))


def dispatch(phrase, *, source, origin_device, satellite, action_results,
             scope, last_lights, registry_factory, context_factory,
             select, execute, follow_on_execute, parse_music, play_music,
             connection, music_inventory, handle_lighting, chained_outcome):
    routine = routine_registry_dispatch.dispatch_routine(
        phrase, source=source, origin_device=origin_device,
        satellite=satellite, action_results=action_results,
        registry_factory=registry_factory, context_factory=context_factory,
        select=select, execute=execute,
    )
    if not routine:
        return None
    follow_on = routine_follow_on_dispatch.execute_follow_on_result(
        routine, origin_device=origin_device, satellite=satellite,
        action_results=action_results, scope=scope,
        execute=follow_on_execute, parse_music=parse_music,
        play_music=play_music, connection=connection,
        music_inventory=music_inventory, handle_lighting=handle_lighting,
        last_lights=last_lights, chained_outcome=chained_outcome,
    )
    return RoutineStageResult(
        reply=follow_on.result.reply, outcome=follow_on.result.outcome,
        routine_status=routine.routine_status,
        routine_turn=routine.routine_selection,
        lighting_context=follow_on.lighting_context,
        routine_voice_result=follow_on.routine_voice_result,
    )
