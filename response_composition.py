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
