"""Pure routing of successful background routine acknowledgements to persona replies."""
from declan.core.execution_results import ExecutionResult, Outcome, parse_outcome
from declan.ai.action_evidence_buffer import evidence_completed
from declan.turn.routine_selection_results import RoutineTurnSelection


def _turn(routine_turn):
    """The typed routine turn, or None when this was not a routine request."""
    return RoutineTurnSelection.coerce(routine_turn) if routine_turn else None


def background_reply(outcome, routine_turn, *, guest, visitor_present, personality):
    """Return a background routine acknowledgement, or None if not applicable."""
    turn = _turn(routine_turn)
    if not (parse_outcome(outcome) is Outcome.STARTED and turn and not turn.follow_on
            and turn.routine.options.get("_declan_background")):
        return None
    options = turn.routine.options
    category = options.get("_declan_reply_category")
    kwargs = {"guest": guest, "visitor_present": visitor_present}
    if category == "morning":
        return personality.morning_request_reply(**kwargs)
    if category == "night":
        return personality.night_request_reply(**kwargs)
    if category == "sexy":
        return personality.sexy_request_reply(options.get("operation", "start"), **kwargs)
    return personality.movie_request_reply(
        options.get("requested_action", options.get("operation", "toggle")), **kwargs)


def routine_reply(reply, *, outcome, routine_turn, routine_voice_result,
                  original_routine_reply, phrase, action_results,
                  guest, visitor_present, render, personality):
    """Apply editable routine response text without overriding previews or safety replies."""
    import re
    decision_outcome = parse_outcome(outcome)
    turn = _turn(routine_turn)
    if not (turn and decision_outcome is not Outcome.PREVIEW
            and not re.match(r"^(?:preview|dry[ -]run)\b", phrase)
            and not any(word in phrase.casefold() for word in (
                "smoke", "fire alarm", "carbon monoxide", "security alert",
                "emergency", "intruder", "panic alarm"))):
        return reply
    if routine_voice_result:
        if isinstance(routine_voice_result, ExecutionResult):
            original, routine_outcome = routine_voice_result.reply, routine_voice_result.outcome
        else:
            original, routine_outcome = routine_voice_result
        reply = render(turn.routine, routine_outcome, original,
                       guest=guest or visitor_present is not False) + original_routine_reply[len(original):]
    else:
        reply = render(turn.routine, outcome, reply,
                       guest=guest or visitor_present is not False)
    if (decision_outcome in {Outcome.CONFIRMED, Outcome.REPORTED_SUCCESS, Outcome.EXECUTION_COMPLETED}
            and turn.routine.options.get("_declan_reply_category") == "dinner"):
        note = personality.dinner_music_feedback(
            action_results, guest=guest, visitor_present=visitor_present)
        if note and note not in reply:
            reply += " " + note
    return reply


def general_reply(reply, *, outcome, routine_reply, routine_turn, light_result,
                  phrase, action_results, guest, visitor_present,
                  personality, lines, parse_music, parse_music_control):
    """Decorate verified general replies exactly once, retaining existing safety gates."""
    import re
    existing_lines = (
        any(line in reply for variants in lines.values()
            for group in variants for line in group)
        or any(line in reply for line in (
            *personality._SAVAGE, *personality._GUEST,
            *personality._DINNER_HOME, *personality._DINNER_GUEST))
    )
    decision_outcome = parse_outcome(outcome)
    verified = decision_outcome is Outcome.REPORTED_SUCCESS and routine_reply is not None and routine_turn is not None
    completed = decision_outcome is Outcome.EXECUTION_COMPLETED and routine_reply is not None and routine_turn is not None
    if not (decision_outcome in (Outcome.CONFIRMED, Outcome.REPORTED_SUCCESS, Outcome.EXECUTION_COMPLETED)
            and not existing_lines and light_result is None and routine_reply is not None
            and (verified or completed or parse_music(phrase) or parse_music_control(phrase)
                 or (action_results and all(evidence_completed(step) for step in action_results)))
            and not re.match(r"^(?:preview|dry[ -]run)\b", phrase)
            and not any(word in phrase.casefold() for word in (
                "smoke", "fire alarm", "carbon monoxide", "security alert",
                "emergency", "intruder", "panic alarm"))):
        return reply
    spoken = "Sorted." if verified else reply
    turn = _turn(routine_turn)
    dinner = bool(turn is not None and (verified or completed)
                  and turn.routine.options.get("_declan_reply_category") == "dinner")
    if dinner and turn is not None and not turn.follow_on:
        spoken = ""
    decorated = personality.decorate(
        spoken, outcome=Outcome.CONFIRMED.value if verified or completed else outcome,
        guest=guest, visitor_present=visitor_present,
        category="dinner" if dinner else "music" if parse_music(phrase) or parse_music_control(phrase)
        else "general",
    )
    if dinner:
        note = personality.dinner_music_feedback(
            action_results, guest=guest, visitor_present=visitor_present)
        if note:
            decorated += " " + note
    return decorated


def lighting_failure_reply(reply, *, light_result, routine_turn, outcome, phrase,
                           response_guest, response_category, parse_light_command,
                           render_failure):
    """Use editable lighting failure text only for non-routine, non-preview failures."""
    import re
    if (light_result is None or routine_turn is not None
            or parse_outcome(outcome) in {Outcome.CONFIRMED, Outcome.PREVIEW}
            or re.match(r"^(?:preview|dry[ -]run)\b", phrase)):
        return reply
    category = response_category(phrase, parse_light_command)
    return render_failure(category, reply, guest=response_guest)
