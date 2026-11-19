"""Home Assistant routine request parsing and selection."""
import re
from declan.turn.routine_selection_results import RoutineSelection, RoutineSelectionKind


def parse_movie_request(phrase, *, rooms, apps):
    shortcut = re.fullmatch(rf"(?:open|launch) (.+?) in (?:the )?({rooms})", phrase)
    if shortcut and shortcut[1] in apps:
        app, room = shortcut.groups()
        return "start", room, app
    match = re.fullmatch(
        r"(?:(start|turn on|end|stop|turn off|toggle) )?(?:movie time|cinema time|cinema mode)"
        rf"(?: in (?:the )?({rooms}))?(?: and (?:open|launch) (.+))?",
        phrase,
    )
    if not match:
        return None
    verb, room, app = match.groups()
    if app:
        app_room = re.fullmatch(rf"(.+?) in (?:the )?({rooms})", app)
        if app_room and room is None:
            app, room = app_room.groups()
    direction = ("start" if verb in ("start", "turn on") else
                 "end" if verb in ("end", "stop", "turn off") else "toggle")
    return direction, room, app


HOUSE_STATUS_REQUESTS = {
    "house status", "home status", "what is the status of the house",
    "what's the status of the house", "what is the house status",
    "what's the house status", "give me a house status",
    "give me the house status", "how is the house",
}


def select_routine_result(phrase, origin, *, connect, discovery_module, movie_parser, morning_phrases, night_phrases, dinner_phrases, sexy_commands):
    """Resolve routine requests exclusively against Home Assistant scripts."""
    phrase = phrase.removeprefix("run ").removeprefix("the ")
    if not 1 <= len(phrase.split()) <= 20:
        return None
    is_house_status = phrase in HOUSE_STATUS_REQUESTS
    connection = connect()
    if connection is None:
        return RoutineSelection(RoutineSelectionKind.HOUSE_STATUS_MISSING) if is_house_status else None
    discovery = discovery_module.discover_result(connection)
    if discovery.error is not None:
        return RoutineSelection(RoutineSelectionKind.HOUSE_STATUS_MISSING) if is_house_status else None
    candidates = [phrase]
    if is_house_status:
        candidates.extend(("house status", "home health summary"))
    if phrase in morning_phrases:
        candidates.append("good morning")
    if phrase in night_phrases:
        candidates.append("good night")
    if phrase.replace("’", "'") in dinner_phrases:
        candidates.extend(("dinner is served", "dinner"))
    if phrase in sexy_commands:
        candidates.append("sexy time")
    movie = movie_parser(phrase)
    if movie:
        direction, room, app = movie
        candidates.extend((f"{direction} movie time",))
        candidates.append("movie time")
        if room:
            candidates.insert(1, f"{direction} movie time {room}")
    for candidate in dict.fromkeys(candidates):
        found = discovery_module.match_result(candidate, discovery.scripts)
        if found.status is not discovery_module.ScriptMatchStatus.NO_MATCH:
            if found.status is discovery_module.ScriptMatchStatus.AMBIGUOUS:
                return RoutineSelection(RoutineSelectionKind.AMBIGUOUS)
            item = found.selected
            # Generic Movie Time is valid for start/end only if HA declares
            # an operation/action field that can distinguish the direction.
            if movie and movie[0] != "toggle" and candidate == "movie time":
                if not set(item.get("fields", [])) & {"operation", "movie_action", "action", "requested_action"}:
                    continue
            if (sexy_commands.get(phrase) == "end" and candidate == "sexy time"
                    and not set(item.get("fields", [])) & {"operation", "requested_action"}):
                continue
            parameters: dict = {}
            if movie:
                parameters = {"operation": movie[0], "movie_action": movie[0],
                              "action": movie[0], "room": movie[1] or "lounge",
                              "movie_room": movie[1] or "lounge"}
                if "requested_action" in item.get("fields", []):
                    parameters["requested_action"] = movie[0]
                parameters["_declan_background"] = True
            elif phrase in morning_phrases or "good morning" in discovery_module.phrases(item):
                parameters = {"_declan_background": True, "_declan_reply_category": "morning"}
            elif phrase in night_phrases or "good night" in discovery_module.phrases(item):
                parameters = {"_declan_background": True, "_declan_reply_category": "night"}
            elif phrase in sexy_commands or "sexy time" in discovery_module.phrases(item):
                parameters = {"operation": sexy_commands.get(phrase, "start"),
                              "_declan_background": True, "_declan_reply_category": "sexy"}
                if "requested_action" in item.get("fields", []):
                    parameters["requested_action"] = parameters["operation"]
            if is_house_status:
                parameters["_declan_expect_response"] = True
            if {"dinner", "dinner is served"} & discovery_module.phrases(item):
                parameters["_declan_reply_category"] = "dinner"
            return RoutineSelection(RoutineSelectionKind.SCRIPT, item["entity_id"], parameters)
    if is_house_status:
        return RoutineSelection(RoutineSelectionKind.HOUSE_STATUS_MISSING)
    return None


