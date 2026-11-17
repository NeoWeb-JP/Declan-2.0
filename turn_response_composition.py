"""Compose a conversation response and attach its existing outcome metadata."""


def compose_turn_response(message, session_id, routine_reply, *,
                          lighting_context, scope, response_guest_mode,
                          outcome, routine_turn, light_result, phrase,
                          action_results, guest_mode, visitor_present,
                          routine_voice_result, routine_status,
                          converse, compose, apply_outcome_metadata,
                          personality, lines, parse_music, parse_music_control,
                          render_routine, response_category, parse_light_command,
                          render_failure, composition):
    """Preserve conversation, response decoration and metadata ordering."""
    reply = converse(message, session_id, routine_reply,
                     lighting_context=lighting_context, scope=scope,
                     guest_mode=response_guest_mode)
    reply["reply"] = compose(
        reply["reply"], outcome=outcome, routine_reply=routine_reply,
        routine_turn=routine_turn, light_result=light_result,
        phrase=phrase, action_results=action_results,
        guest=guest_mode != "off",
        response_guest=response_guest_mode != "off",
        visitor_present=visitor_present,
        routine_voice_result=routine_voice_result,
        personality=personality, lines=lines,
        parse_music=parse_music, parse_music_control=parse_music_control,
        render_routine=render_routine, response_category=response_category,
        parse_light_command=parse_light_command,
        render_failure=render_failure, composition=composition,
    )
    apply_outcome_metadata(reply, outcome=outcome, routine_status=routine_status)
    return reply
