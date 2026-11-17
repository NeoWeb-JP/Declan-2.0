"""Chained routine follow-on actions, independent of HTTP request handling."""
from dataclasses import dataclass
from execution_results import ExecutionResult, Outcome
from music_provider_result import music_execution_result
from command_response import CommandResponse


@dataclass(frozen=True)
class FollowOnResult:
    reply: str
    outcome: Outcome
    lighting_context: tuple[str, ...]
    routine_voice_result: tuple[str, str]

    def __post_init__(self):
        object.__setattr__(self, "outcome", Outcome(self.outcome))


def execute_result(follow_on, *, routine_result, routine_status,
            parse_music, play_music, connection, music_inventory,
            handle_lighting, last_lights, origin, music_origin,
            action_results, scope, chained_outcome):
    """Execute a follow-on once and preserve the existing action and reply semantics."""
    if not isinstance(routine_result, ExecutionResult):
        raise ValueError("Routine follow-on requires a typed execution result")
    routine_reply, routine_outcome = routine_result.reply, routine_result.outcome
    light_steps = []
    if follow_on.startswith("play "):
        command = parse_music(follow_on)
        follow_result = music_execution_result(
            play_music(command, connection(), music_inventory,
                       **({"origin": music_origin} if music_origin else {}))
            if command else ("Tell me where to play the music.", "unresolved")
        )
    else:
        lighting_result = handle_lighting(
            follow_on, action_results=light_steps, last_lights=last_lights,
            origin_device=origin,
        )
        follow_result = (lighting_result if isinstance(lighting_result, ExecutionResult)
                         else ExecutionResult(*(lighting_result or (
                             "I couldn't understand the lighting command after the routine.", "unresolved"
                         ))))
    follow_reply, follow_outcome = follow_result.reply, follow_result.outcome
    action_results.extend(light_steps)
    lighting_context = ()
    if follow_outcome is Outcome.CONFIRMED and scope is not None and len(light_steps) < 200:
        lighting_context = tuple(dict.fromkeys(
            step["entity_id"] for step in light_steps
            if step["status"] in ("confirmed", "already_set") and "entity_id" in step
        ))
    if routine_status and routine_status not in routine_reply:
        routine_reply += f" {routine_status}"
    routine_reply += f" {follow_reply}"
    return CommandResponse(
        ExecutionResult(routine_reply, chained_outcome(routine_outcome, follow_outcome),
                        routine_result.actions + follow_result.actions),
        lighting_context=lighting_context, routine_voice_result=routine_result,
    )


def execute(follow_on, *, routine_reply, routine_outcome, routine_status,
            parse_music, play_music, connection, music_inventory,
            handle_lighting, last_lights, origin, music_origin,
            action_results, scope, chained_outcome):
    """Compatibility API for the existing follow-on result attributes."""
    response = execute_result(
        follow_on, routine_result=ExecutionResult(routine_reply, routine_outcome),
        routine_status=routine_status, parse_music=parse_music, play_music=play_music,
        connection=connection, music_inventory=music_inventory,
        handle_lighting=handle_lighting, last_lights=last_lights, origin=origin,
        music_origin=music_origin, action_results=action_results, scope=scope,
        chained_outcome=chained_outcome,
    )
    return FollowOnResult(response.result.reply, response.result.outcome,
                          response.lighting_context, response.routine_voice_result.as_legacy_pair())
