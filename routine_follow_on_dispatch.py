"""Run optional routine follow-on actions and preserve response context."""


def execute_follow_on(dispatch, *, origin_device, satellite, action_results,
                      scope, execute, parse_music, play_music, connection,
                      music_inventory, handle_lighting, last_lights,
                      chained_outcome):
    """Return (reply, outcome, lighting_context, voice_result) for a routine."""
    reply, outcome = dispatch.result.as_legacy_pair()
    follow_on = dispatch.routine_follow_on
    if not follow_on:
        return reply, outcome, (), None
    chained = execute(
        follow_on, routine_reply=reply, routine_outcome=outcome,
        routine_status=dispatch.routine_status, parse_music=parse_music,
        play_music=play_music, connection=connection,
        music_inventory=music_inventory, handle_lighting=handle_lighting,
        last_lights=last_lights, origin=origin_device or satellite,
        music_origin=satellite or origin_device, action_results=action_results,
        scope=scope, chained_outcome=chained_outcome,
    )
    return chained.reply, chained.outcome, chained.lighting_context, chained.routine_voice_result
