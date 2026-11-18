"""Execute follow-on routine actions and expose their typed response context."""
from dataclasses import dataclass


@dataclass(frozen=True)
class RoutineFollowOnOutcome:
    reply: str
    outcome: object
    lighting_context: object
    routine_voice_result: object


def execute_routine_follow_on(
    routine_dispatch, *, origin_device, satellite, action_results, scope,
    execute_follow_on, execute, parse_music, play_music, connection,
    music_inventory, handle_lighting, last_lights, chained_outcome,
):
    response = execute_follow_on(
        routine_dispatch, origin_device=origin_device, satellite=satellite,
        action_results=action_results, scope=scope, execute=execute,
        parse_music=parse_music, play_music=play_music, connection=connection,
        music_inventory=music_inventory, handle_lighting=handle_lighting,
        last_lights=last_lights, chained_outcome=chained_outcome,
    )
    return RoutineFollowOnOutcome(
        reply=response.result.reply, outcome=response.result.outcome,
        lighting_context=response.lighting_context,
        routine_voice_result=response.routine_voice_result,
    )
