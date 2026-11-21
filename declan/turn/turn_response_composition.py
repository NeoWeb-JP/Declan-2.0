"""Compose a conversation response and attach its existing outcome metadata."""
from declan.turn.turn_response import TurnResponse
from declan.core.execution_results import Outcome


def compose_turn_result(message, session_id, routine_reply, *,
                          lighting_context, scope, response_guest_mode,
                          outcome, routine_turn, light_result, phrase,
                          action_results, guest_mode, visitor_present,
                          routine_voice_result, routine_status,
                          converse, compose, apply_outcome_metadata,
                          personality, lines, parse_music, parse_music_control,
                          render_routine, response_category, parse_light_command,
                          render_failure, composition):
    """Preserve conversation, response decoration and metadata ordering."""
    outcome = Outcome(outcome) if outcome is not None else None
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
    from declan.turn.command_vocabulary import GUEST_HINT, UNMATCHED_REPLY
    if guest_mode != "off" and reply.get("reply") == UNMATCHED_REPLY:
        reply["reply"] = UNMATCHED_REPLY + GUEST_HINT
    return TurnResponse(reply, outcome, routine_status)


def compose_turn_response(message, session_id, routine_reply, *,
                          lighting_context, scope, response_guest_mode,
                          outcome, routine_turn, light_result, phrase,
                          action_results, guest_mode, visitor_present,
                          routine_voice_result, routine_status,
                          converse, compose, apply_outcome_metadata,
                          personality, lines, parse_music, parse_music_control,
                          render_routine, response_category, parse_light_command,
                          render_failure, composition):
    """Compatibility API returning the existing final response mapping."""
    result = compose_turn_result(message, session_id, routine_reply,
                                 lighting_context=lighting_context,
                                 scope=scope,
                                 response_guest_mode=response_guest_mode,
                                 outcome=outcome,
                                 routine_turn=routine_turn,
                                 light_result=light_result,
                                 phrase=phrase,
                                 action_results=action_results,
                                 guest_mode=guest_mode,
                                 visitor_present=visitor_present,
                                 routine_voice_result=routine_voice_result,
                                 routine_status=routine_status,
                                 converse=converse,
                                 compose=compose,
                                 apply_outcome_metadata=apply_outcome_metadata,
                                 personality=personality,
                                 lines=lines,
                                 parse_music=parse_music,
                                 parse_music_control=parse_music_control,
                                 render_routine=render_routine,
                                 response_category=response_category,
                                 parse_light_command=parse_light_command,
                                 render_failure=render_failure,
                                 composition=composition,
    )
    return result.to_wire(apply_outcome_metadata)
