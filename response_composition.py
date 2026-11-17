"""Pure routing of successful background routine acknowledgements to persona replies."""


def background_reply(outcome, routine_turn, *, guest, visitor_present, personality):
    """Return a background routine acknowledgement, or None if not applicable."""
    if not (outcome == "started" and routine_turn and not routine_turn[1]
            and routine_turn[0][1].get("_declan_background")):
        return None
    options = routine_turn[0][1]
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
    if not (routine_turn and outcome != "preview"
            and not re.match(r"^(?:preview|dry[ -]run)\b", phrase)
            and not any(word in phrase.casefold() for word in (
                "smoke", "fire alarm", "carbon monoxide", "security alert",
                "emergency", "intruder", "panic alarm"))):
        return reply
    if routine_voice_result:
        original, routine_outcome = routine_voice_result
        reply = render(routine_turn[0], routine_outcome, original,
                       guest=guest or visitor_present is not False) + original_routine_reply[len(original):]
    else:
        reply = render(routine_turn[0], outcome, reply,
                       guest=guest or visitor_present is not False)
    if (outcome in {"confirmed", "reported_success", "execution_completed"}
            and routine_turn[0][1].get("_declan_reply_category") == "dinner"):
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
    verified = outcome == "reported_success" and routine_reply is not None and routine_turn is not None
    completed = outcome == "execution_completed" and routine_reply is not None and routine_turn is not None
    if not (outcome in ("confirmed", "reported_success", "execution_completed")
            and not existing_lines and light_result is None and routine_reply is not None
            and (verified or completed or parse_music(phrase) or parse_music_control(phrase)
                 or (action_results and all(step.get("status") in
                     {"confirmed", "already_set", "completed"} for step in action_results)))
            and not re.match(r"^(?:preview|dry[ -]run)\\b", phrase)
            and not any(word in phrase.casefold() for word in (
                "smoke", "fire alarm", "carbon monoxide", "security alert",
                "emergency", "intruder", "panic alarm"))):
        return reply
    spoken = "Sorted." if verified else reply
    dinner = bool(routine_turn is not None and (verified or completed)
                  and routine_turn[0][1].get("_declan_reply_category") == "dinner")
    if dinner and not routine_turn[1]:
        spoken = ""
    decorated = personality.decorate(
        spoken, outcome="confirmed" if verified or completed else outcome,
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
