"""Chained routine follow-on actions, independent of HTTP request handling."""
from dataclasses import dataclass
from execution_results import ExecutionResult, Outcome
from declan.music.music_provider_result import music_execution_result
from command_response import CommandResponse
from declan.ha.lighting_action_evidence import confirmed_lighting_entities
from action_evidence_buffer import ActionEvidenceBuffer, extend_action_evidence


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
    light_steps = ActionEvidenceBuffer()
    if follow_on.startswith("play "):
        command = parse_music(follow_on)
        if command:
            follow_result = music_execution_result(
                play_music(command, connection(), music_inventory,
                           **({"origin": music_origin} if music_origin else {})))
        else:
            follow_result = ExecutionResult("Tell me where to play the music.", Outcome.UNRESOLVED)
    else:
        lighting_result = handle_lighting(
            follow_on, action_results=light_steps, last_lights=last_lights,
            origin_device=origin,
        )
        if isinstance(lighting_result, ExecutionResult):
            follow_result = lighting_result
        elif lighting_result:
            follow_result = ExecutionResult(*lighting_result)
        else:
            follow_result = ExecutionResult(
                "I couldn't understand the lighting command after the routine.", Outcome.UNRESOLVED)
    follow_reply, follow_outcome = follow_result.reply, follow_result.outcome
    extend_action_evidence(action_results, light_steps)
    lighting_context = ()
    if follow_outcome is Outcome.CONFIRMED and scope is not None and len(light_steps) < 200:
        lighting_context = confirmed_lighting_entities(light_steps)
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
