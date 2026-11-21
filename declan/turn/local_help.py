"""Free, local answers about what Declan can do here (no AI, works with Conversation off).

"What can you do?", "which lights are in here?", "what routines are there?",
"what rooms do you know?" and "where can you play music?" are answered from
Home Assistant data Declan already reads. Nothing is changed and nothing is
sent anywhere.
"""
import re

HELP = re.compile(r"(?:what can (?:you|i) (?:do|say|ask(?: you)?)|what do you do|help(?: me)?|how do i use you|"
                  r"what are you able to do|what can you help (?:me )?with)")
LIGHTS = re.compile(r"(?:what|which) (?:lights|lamps|devices|things)(?: can (?:you|i) (?:control|turn on))?"
                    r" (?:are )?(?:there )?(?:in here|in this room|here|in (?:the )?(?P<room>.+?))(?: can you control)?")
ROUTINES = re.compile(r"(?:what|which) routines (?:are there|do you have|can you (?:run|do)|have you got)|"
                      r"list (?:the |your )?routines")
ROOMS = re.compile(r"(?:what|which) rooms (?:do you know|are there|can you control|have you got)")
SPEAKERS = re.compile(r"(?:where can you play music|(?:what|which) speakers (?:are there|do you have|can you use)|"
                      r"where can i play music)")
MAX_LISTED = 8


def match(phrase):
    if not isinstance(phrase, str):
        return None
    text = " ".join(phrase.casefold().replace("’", "'").split()).strip(" ?.!")
    text = re.sub(r"^(?:declan,? |hey declan,? |please )", "", text)
    if HELP.fullmatch(text):
        return ("help", None)
    lights = LIGHTS.fullmatch(text)
    if lights:
        return ("lights", lights["room"])
    if ROUTINES.fullmatch(text):
        return ("routines", None)
    if ROOMS.fullmatch(text):
        return ("rooms", None)
    if SPEAKERS.fullmatch(text):
        return ("speakers", None)
    return None


def _names(values):
    values = [value for value in values if value]
    if len(values) > MAX_LISTED:
        values = values[:MAX_LISTED] + [f"{len(values) - MAX_LISTED} more"]
    if len(values) <= 1:
        return "".join(values)
    return ", ".join(values[:-1]) + " and " + values[-1]


def _friendly(row):
    attributes = row.get("attributes") if isinstance(row.get("attributes"), dict) else {}
    return str(attributes.get("friendly_name") or row["entity_id"].split(".", 1)[1].replace("_", " "))


GUEST_HELP = ("Easy. Say \"lights on\" or \"lights off\", \"play some music\", \"louder\" or \"quieter\", "
              "and \"stop\". I'll do it in the room you're in.")


def answer(request, *, rows, context, conversation_on, guest=False):
    """Spoken answer for a matched help request."""
    kind, room = request
    if kind == "help" and guest:
        return GUEST_HELP + (" Or just tell me what you want." if conversation_on else "")
    music_rooms = sorted(r for r in context["music_rooms"] if r not in {"upstairs", "downstairs"})
    routines = sorted(context["routines"])
    if kind == "help":
        parts = ["I can switch lights, fans and blinds on and off and dim them, play music"]
        speakers = [r for r in music_rooms if r != "everywhere"]
        if speakers:
            parts[0] += " in the " + _names(speakers[:4]) + " or everywhere"
        parts[0] += ", change the volume, set timers"
        if routines:
            parts[0] += ", and run routines like " + _names(routines[:3])
        reply = parts[0] + "."
        reply += (" Just say what you want in your own words." if conversation_on
                  else " Try \"turn on the kitchen lights\" or \"play jazz in the kitchen\".")
        return reply
    if kind == "lights":
        target = (room or context.get("you_are_in") or "").casefold().removeprefix("the ").strip()
        if not target:
            return "Which room? Say, for example, \"which lights are in the kitchen\"."
        found = sorted({_friendly(row) for row in rows if isinstance(row, dict)
                        and str(row.get("entity_id", "")).split(".", 1)[0] in {"light", "switch", "fan", "cover"}
                        and str(row.get("declan_area") or "").casefold() == target})
        label = "in here" if not room else f"in the {target}"
        return (f"{label.capitalize()}: {_names(found)}." if found
                else f"I can't see any lights or devices {label}.")
    if kind == "routines":
        return f"I can run {_names(routines)}." if routines else "I can't see any routines in Home Assistant."
    if kind == "rooms":
        rooms = sorted({str(r) for r in context["areas"] if r})
        return f"I know these rooms: {_names(rooms)}." if rooms else "I can't see any rooms in Home Assistant."
    if kind == "speakers":
        speakers = [r for r in music_rooms if r != "everywhere"]
        return (f"I can play music in the {_names(speakers)}, or everywhere." if speakers
                else "No music speakers are set up yet. Add them in Settings → Media players.")
    return None
