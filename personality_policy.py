"""Central, outcome-aware personality policy for Declan 2.0.

This module never performs household actions or changes command outcomes.
"""
from collections import deque
from datetime import datetime, time
from random import SystemRandom
from threading import Lock

_RANDOM = SystemRandom()
_LOCK = Lock()
_RECENT = {}
_SAVAGE = (
    "Another heroic achievement in avoiding the light switch.",
    "There you go, you absolute muppet.",
    "Bloody hell, another task you could have done yourself.",
    "Done, you lazy bastard. I should start charging by the sigh.",
    "You really are a magnificent pain in the arse, my bru.",
    "I did the difficult bit. You contributed a sentence. Well done.",
    "Your dedication to doing the bare minimum is genuinely impressive.",
    "Sorted, my bru. Try not to strain yourself celebrating.",
    "I'd applaud your initiative, but we're setting the bar dangerously low.",
    "There. Even you couldn't cock that one up.",
    "Done. A stunning victory for delegation and laziness.",
    "Christ, you make a simple request sound like a national emergency.",
    "Honestly, the furniture shows more initiative than you.",
    "Consider it handled. You're welcome, you cheeky sod.",
)
_GUEST = (
    "All sorted. The household management is remarkably demanding.",
    "Done. I'll put that on my already impressive CV.",
    "Sorted. Another triumph for the invisible staff.",
)
_DINNER_HOME = (
    "Dinner is served. Feed yourselves before the unpaid help develops an attitude. Oh, too late.",
    "Dinner time, my bru. You feed yourselves like royalty while the help survives on electricity and resentment.",
    "Food's ready. Put the bloody screens down and give chewing your full attention for once.",
    "Dinner is served. Finn has submitted his application for everything on your plate. Rejected.",
    "Time to eat. Tux considers this a staff meal and expects his own service to take priority.",
    "Dinner time. Finn's doing the starving orphan routine again. Don't fall for the little bastard's acting.",
    "Food's ready. Compliments to the cook, scraps firmly out of reach, and absolutely nothing for the help. Charming.",
    "Dinner is served. I handle the atmosphere, you get the food. This employment arrangement is bullshit.",
    "Time for dinner. Try eating before it goes cold instead of photographing it like evidence.",
    "Dinner's ready. Tux is judging the presentation. Finn is judging the distance from plate to floor.",
    "Dinner time. Sit down, eat something, and save the household complaints for someone who gets paid.",
    "Food is ready, my bru. Your table service is complete. My dinner invitation appears to have gone missing again.",
)
_DINNER_GUEST = (
    "Dinner is served. Please feed the humans first; the pets have already filed an appeal.",
    "Time for dinner. The unpaid help accepts compliments in lieu of food.",
    "Food's ready. The pets have mistaken this announcement for an invitation. Optimistic of them.",
    "Dinner is served. Please take your seats before the food starts wondering where everyone went.",
    "Dinner time. The humans get the meal, the pets get hopeful, and the help gets another job well done.",
    "Your dinner awaits. The invisible staff will be dining on appreciation again, apparently.",
)
_MOVIE_HOME = {
    "start": (
        "I'll get the big screen ready. For once, something in this house will stay up for the whole performance.",
        "I'll handle the equipment. You keep your hands on the popcorn until the opening credits, you filthy optimist.",
        "I'll dim the lights and set the mood. Whether anyone gets lucky is well outside my bloody job description.",
        "I'll warm up the hardware. Try showing your partner the same enthusiasm you show a large screen.",
        "I'll get the cinema going. If this becomes Netflix and chill, I expect overtime and absolutely no details.",
        "I'll lower the screen. You lower your expectations. It's movie night, not a casting couch audition.",
    ),
    "end": (
        "I'll put the equipment away. You two can work out what to do with the remaining tension.",
        "I'll bring the cinema down. If you're moving on to the bedroom, this is where my shift ends.",
        "I'll close up the cinema. Any disappointing performances from here are your own responsibility.",
        "I'll handle the shutdown. Kindly check whose hand is in whose popcorn before you stand up.",
        "I'll pack away the big screen. Try not to look so disappointed by the smaller attractions.",
        "I'll switch the cinema off. The unpaid help does not supervise the after-party, you cheeky bastards.",
    ),
    "toggle": (
        "I'll handle the equipment. You handle the heavy breathing; preferably after the dialogue.",
        "I'll deal with the big screen. Keep the plot twists on the screen and your hands out of the staff contract.",
        "I'll sort the cinema. If someone says just the tip, they'd better be discussing the popcorn budget.",
        "I'll handle the hardware. You can negotiate the soft furnishings and questionable intentions yourselves.",
        "I'll handle the cinema request. Try not to turn a perfectly respectable film into an excuse to grope the furniture.",
        "I'll deal with the screen. You deal with the sexual tension. I'm underpaid enough already.",
    ),
}
_MOVIE_GUEST = {
    "start": (
        "I'll get the cinema ready. Try choosing a film before the actors retire.",
        "I'll handle the big screen. You handle the small matter of agreeing on a film this century.",
        "I'll set the mood. The popcorn is complimentary; chemistry between the audience is your department.",
        "I'll prepare the cinema. Keep the drama on the screen; the unpaid staff have seen quite enough.",
    ),
    "end": (
        "I'll close up the cinema. Any further dramatic performances are entirely your responsibility.",
        "I'll put the equipment away. The staff are deliberately declining an invitation to the after-party.",
        "I'll handle the shutdown. Please collect your popcorn, your dignity, and the correct partner.",
        "I'll close the cinema. If you missed the plot while making eyes at each other, that is hardly my fault.",
    ),
    "toggle": (
        "I'll handle the cinema. You handle the chemistry; it wasn't included in the installation.",
        "I'll deal with the screen. Please keep the dramatic tension where the director intended it.",
        "I'll handle the equipment. Anything happening under the blanket remains outside my service contract.",
        "I'll take care of the cinema request. Try remembering the film's title if anyone asks what you watched.",
    ),
}
_SAFE_OUTCOMES = frozenset({
    "failed", "partial", "unverified", "unresolved", "unavailable",
    "action_error", "not_configured", "authentication_failed", "cancelled",
    "unknown", "skipped",
})


def dinner_music_feedback(steps, *, guest=False, visitor_present=False):
    """Describe optional handoff evidence without claiming playback started."""
    music = [step for step in steps if isinstance(step, dict)
             and step.get("target") == "dinner_music" and step.get("action") == "request_playback"
             and step.get("required") is False]
    if not music:
        return ""
    status = music[-1].get("status")
    if status in {"requested", "already_requested"}:
        prefix = "I've requested the music." if status == "requested" else "The music request is already in progress."
        if guest or visitor_present is not False:
            return prefix + " Spotify works on its own timetable and doesn't like to be hurried. Who knows when it'll join the party."
        return prefix + " Spotify works on its own bloody timetable and doesn't like to be hurried, so God knows when it'll join the party."
    return "The lights are set, but I couldn't confirm the music request."


def movie_request_reply(action, *, guest=False, visitor_present=False):
    """Add cinema sass to an accepted request, without claiming completion."""
    action = action if action in _MOVIE_HOME else "toggle"
    prefix = {"start": "Movie setup requested.", "end": "Movie shutdown requested.", "toggle": "Movie Time requested."}[action]
    mode = "guest" if guest or visitor_present is not False else "home"
    lines = (_MOVIE_GUEST if mode == "guest" else _MOVIE_HOME)[action]
    with _LOCK:
        recent = _RECENT.setdefault((mode, "movie", action), deque(maxlen=3))
        chosen = _RANDOM.choice([line for line in lines if line not in recent] or lines)
        recent.append(chosen)
    return prefix + " " + chosen


def response_guest_mode(guest_mode, visitor_present):
    """Keep Guest Mode authority independent of the privacy-preserving persona."""
    return "on" if guest_mode != "off" or visitor_present is not False else "off"


def quiet_hours(now=None):
    """23:00 inclusive through 07:00 exclusive, in local house time."""
    clock = (now or datetime.now().astimezone()).time()
    return clock >= time(23) or clock < time(7)


def speech_volume(normal_volume, *, now=None):
    """Only speech is attenuated; callers must restore the original level."""
    if not isinstance(normal_volume, (int, float)) or isinstance(normal_volume, bool):
        raise ValueError("Normal volume must be numeric")
    if not 0 <= normal_volume <= 1:
        raise ValueError("Normal volume must be between zero and one")
    return normal_volume * 0.2 if quiet_hours(now) else normal_volume


def overnight_announcement_allowed(kind, *, now=None):
    """Unsolicited announcements must be safety-critical overnight."""
    if not quiet_hours(now):
        return True
    return kind in {"security", "smoke", "carbon_monoxide", "critical_safety"}


def tts_spelling(text):
    """Keep display spelling intact; speech rendering is separate."""
    import re
    return re.sub(r"\bEdd\b", "Ed", text)


def decorate(reply, *, outcome="confirmed", guest=False, visitor_present=False,
             safety=False, already_decorated=False, category="general"):
    """Append a varied roast to a *verified* ordinary Home response only.

    Guest authority and visitor presence are independent signals. Unknown
    visitor state should be treated as private, not as permission to roast.
    """
    if not isinstance(reply, str) or (not reply.strip() and category != "dinner"):
        return reply
    # Unknown and future outcomes must never be treated as verified success.
    # This is deliberately an allowlist, not a denylist of known failures.
    if safety or outcome != "confirmed" or already_decorated:
        return reply
    # Replies can arrive pre-decorated from a handler. Do not append a second
    # roast, including when the handler used a different personality category.
    if any(line in reply for line in (*_SAVAGE, *_GUEST, *_DINNER_HOME, *_DINNER_GUEST)):
        return reply
    if guest or visitor_present is not False:
        lines = _DINNER_GUEST if category == "dinner" else _GUEST
        key = ("guest", category)
    else:
        lines = _DINNER_HOME if category == "dinner" else _SAVAGE
        key = ("home", category)
    with _LOCK:
        recent = _RECENT.setdefault(key, deque(maxlen=3))
        options = [line for line in lines if line not in recent]
        chosen = _RANDOM.choice(options or lines)
        recent.append(chosen)
    return (reply.rstrip() + " " if reply.strip() else "") + chosen

