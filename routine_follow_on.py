"""Chained routine follow-on actions, independent of HTTP request handling."""
from dataclasses import dataclass


@dataclass(frozen=True)
class FollowOnResult:
    reply: str
    outcome: str
    lighting_context: tuple[str, ...]
    routine_voice_result: tuple[str, str]


def execute(follow_on, *, routine_reply, routine_outcome, routine_status,
            parse_music, play_music, connection, music_inventory,
            handle_lighting, last_lights, origin, music_origin,
            action_results, scope, chained_outcome):
    """Execute a follow-on once and preserve the existing action and reply semantics."""
    light_steps = []
    if follow_on.startswith("play "):
        command = parse_music(follow_on)
        follow_reply, follow_outcome = (
            play_music(command, connection(), music_inventory,
                       **({"origin": music_origin} if music_origin else {}))
            if command else ("Tell me where to play the music.", "unresolved")
        )
    else:
        lighting_result = handle_lighting(
            follow_on, action_results=light_steps, last_lights=last_lights,
            origin_device=origin,
        )
        follow_reply, follow_outcome = lighting_result or (
            "I couldn't understand the lighting command after the routine.", "unresolved"
        )
    action_results.extend(light_steps)
    lighting_context = ()
    if follow_outcome == "confirmed" and scope is not None and len(light_steps) < 200:
        lighting_context = tuple(dict.fromkeys(
            step["entity_id"] for step in light_steps
            if step["status"] in ("confirmed", "already_set") and "entity_id" in step
        ))
    original_reply = routine_reply
    if routine_status and routine_status not in routine_reply:
        routine_reply += f" {routine_status}"
    routine_reply += f" {follow_reply}"
    return FollowOnResult(
        routine_reply, chained_outcome(routine_outcome, follow_outcome),
        lighting_context, (original_reply, routine_outcome),
    )
