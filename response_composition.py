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
            and not re.match(r"^(?:preview|dry[ -]run)\\b", phrase)
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
