"""Ordered spoken-response composition for completed HTTP turns."""


def compose(reply, *, outcome, routine_reply, routine_turn, light_result,
            phrase, action_results, guest, response_guest, visitor_present,
            routine_voice_result, personality, lines, parse_music,
            parse_music_control, render_routine, response_category,
            parse_light_command, render_failure, composition):
    """Preserve the general, background, routine and lighting precedence."""
    spoken = composition.general_reply(
        reply, outcome=outcome, routine_reply=routine_reply,
        routine_turn=routine_turn, light_result=light_result,
        phrase=phrase, action_results=action_results,
        guest=guest, visitor_present=visitor_present,
        personality=personality, lines=lines,
        parse_music=parse_music, parse_music_control=parse_music_control,
    )
    background = composition.background_reply(
        outcome, routine_turn, guest=guest,
        visitor_present=visitor_present, personality=personality,
    )
    if background is not None:
        spoken = background
    spoken = composition.routine_reply(
        spoken, outcome=outcome, routine_turn=routine_turn,
        routine_voice_result=routine_voice_result,
        original_routine_reply=routine_reply, phrase=phrase,
        action_results=action_results, guest=guest,
        visitor_present=visitor_present, render=render_routine,
        personality=personality,
    )
    return composition.lighting_failure_reply(
        spoken, light_result=light_result, routine_turn=routine_turn,
        outcome=outcome, phrase=phrase, response_guest=response_guest,
        response_category=response_category,
        parse_light_command=parse_light_command, render_failure=render_failure,
    )
