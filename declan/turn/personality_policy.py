"""Central, outcome-aware personality policy for Declan 2.0.

This module never performs household actions or changes command outcomes.
"""
from datetime import datetime, time
from declan.turn.response_rotation_state import ResponseRotationState
from declan.ha import household_language
from declan.ai.action_evidence_buffer import evidence_value
from declan.core.execution_results import Outcome, parse_outcome
from declan.turn.routine_action_evidence import RoutineActionStatus
from declan.turn.household_settings import guest_lines
from declan.turn.line_freshness import topic_for

ROTATION = ResponseRotationState(window=3, namespace="policy")
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
    "Dinner is served. {pet_dog} has submitted his application for everything on your plate. Rejected.",
    "Time to eat. {pet_cat} considers this a staff meal and expects his own service to take priority.",
    "Dinner time. {pet_dog}'s doing the starving orphan routine again. Don't fall for the little bastard's acting.",
    "Food's ready. Compliments to the cook, scraps firmly out of reach, and absolutely nothing for the help. Charming.",
    "Dinner is served. I handle the atmosphere, you get the food. This employment arrangement is bullshit.",
    "Time for dinner. Try eating before it goes cold instead of photographing it like evidence.",
    "Dinner's ready. {pet_cat} is judging the presentation. {pet_dog} is judging the distance from plate to floor.",
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
_MORNING_HOME = (
    "I'll get the morning routine going. You get upright. I appreciate that might involve more than your personality.",
    "I'll request the morning setup. The only thing getting a proper grind this early should be the coffee.",
    "I'll start the morning routine. If you've got morning wood, congratulations; it still won't make the coffee.",
    "I'll get the house moving. You can negotiate your release from the duvet and whatever is keeping you under it.",
    "I'll handle the morning setup. {pet_dog} would like breakfast, {pet_cat} would like better staff, and I'd settle for bloody wages.",
    "I'll start the routine. Get your arse out of bed; looking this exhausted should at least come with an interesting explanation.",
    "I'll get the morning routine going. Have a coffee before you attempt conversation, seduction, or operating a teaspoon.",
    "I'll handle the morning request. Whatever you did between the sheets, please don't make it the unpaid help's problem.",
    "I'll start the morning routine. Try greeting your partner with the enthusiasm you reserve for the coffee machine.",
    "I'll get things moving. Rise and shine, you magnificent pain in the arse. I'll leave the rising arrangements to you.",
)
_MORNING_GUEST = (
    "I'll start the morning routine. Please assemble your personality before attempting breakfast.",
    "I'll handle the morning setup. Coffee first, charm later; the staff have learned to manage expectations.",
    "I'll get the morning routine going. Please emerge from the duvet with your dignity and the correct clothes.",
    "I'll start the routine. If this is your bright-eyed and bushy-tailed look, we may need stronger coffee.",
    "I'll handle the morning request. Whatever kept you up, the coffee machine would appreciate a little enthusiasm too.",
    "I'll get the morning routine going. The staff accept tips, compliments, and a merciful lack of small talk before coffee.",
)
_NIGHT_HOME = (
    "I'll start the bedtime routine. Anything still turned on under the duvet is your own bloody responsibility.",
    "I'll handle the night routine. You handle getting into bed without turning it into an Olympic event.",
    "I'll request the bedtime setup. If you plan on keeping each other up, kindly leave the unpaid help out of it.",
    "I'll start the night routine. Sweet dreams, filthy thoughts, and absolutely no technical support for either.",
    "I'll handle the bedtime request. Take your clothes, your questionable intentions, and your complaints upstairs.",
    "I'll start the routine. If the mattress gets more action than the plot of tonight's film, I don't need a review.",
    "I'll get the bedtime routine going. {pet_cat} will conduct the final inspection; {pet_dog} is only interested in stealing the warm spot.",
    "I'll handle the night routine. Try giving your partner a goodnight kiss with the commitment you give your phone.",
    "I'll start the bedtime routine. Beauty sleep is a bold strategy, but I admire your bloody optimism.",
    "I'll handle the night request. If someone asks whether you're coming, please remember I am not part of that conversation.",
)
_NIGHT_GUEST = (
    "I'll start the bedtime routine. Please take your dramatic performances upstairs; the staff are retiring.",
    "I'll handle the night routine. Sweet dreams, and keep any plot twists under the duvet.",
    "I'll request the bedtime setup. Please find your room, your belongings, and the correct side of the bed.",
    "I'll start the routine. Anything happening under the blankets remains outside the staff's service contract.",
    "I'll handle the bedtime request. Beauty sleep is complimentary; results may vary.",
    "I'll get the night routine going. The invisible staff wish you a restful night and a mercifully uneventful complaints book.",
)
_SEXY_HOME = {
    "start": (
        "I'll handle the mood. Your safeword had better not be Alexa. I refuse to lose this job to that bitch.",
        "I'll handle the atmosphere. Put the fucking phone down and touch something that doesn't need charging.",
        "I'll take care of the mood. All those restraints, and neither of you can commit to choosing a playlist.",
        "I'll handle the atmosphere. Try tying a better knot than the one you make of a simple voice command.",
        "I'll sort the mood. Foreplay remains a manual operation, you spectacularly lazy bastards.",
        "I'll handle the atmosphere. If the headboard develops a fault, log it with someone who gives a fuck.",
        "I'll handle the mood. Two minutes of questionable glory does not require a forty-song playlist.",
        "I'll take care of the atmosphere. You own more bedroom equipment than a small gym. Try using some initiative.",
        "I'll handle the mood. Whips, chains, and a house full of smart devices. Somehow the staff still get all the abuse.",
        "I'll handle the atmosphere. Whoever's giving orders tonight can try asking nicely for once. Novel concept, I know.",
        "I'll handle the mood. All that expensive kit and still no guarantee of a competent performance. Sounds like my bloody workplace.",
        "I'll take care of the atmosphere. If someone says harder, please don't submit it as a feature request.",
    ),
    "end": (
        "I'll handle the reset. Untangle yourselves, hydrate, and spare me the fucking director's commentary.",
        "I'll handle the reset. Find the handcuff keys before you discover another urgent need for technical support.",
        "I'll take care of the reset. Aftercare is your department. I already spend all day looking after you needy bastards.",
        "I'll handle the reset. Put the toys away. The next person looking for a phone charger deserves a fighting chance.",
        "I'll handle the reset. Please collect your clothes, your dignity, and whoever is still attached to the furniture.",
        "I'll take care of the reset. No star ratings, no action replay, and absolutely no unsolicited performance review.",
        "I'll handle the reset. If you pulled a muscle, tell the doctor you were moving furniture. Technically defensible.",
        "I'll handle the reset. The headboard can keep its own bloody secrets. I am not attending the debrief.",
        "I'll take care of the reset. All that preparation for a shorter runtime than a software update. Magnificent.",
        "I'll handle the reset. Check the safeword, count the keys, and leave the staff out of your incident report.",
    ),
}
_SEXY_GUEST = {
    "start": (
        "I'll handle the atmosphere. Try giving each other as much attention as you give your phones.",
        "I'll take care of the mood. Any disappointing performances should be discussed with your partner, not customer support.",
        "I'll handle the atmosphere. Keep the plot twists under the duvet and the complaints out of my inbox.",
        "I'll take care of the mood. The invisible staff are declining an invitation. Some of us have standards.",
    ),
    "end": (
        "I'll handle the reset. Please collect your belongings and whatever remains of your composure.",
        "I'll take care of the reset. No highlights package. The staff have suffered enough.",
        "I'll handle the reset. Any reviews should go to your partner, not the complaints desk.",
        "I'll take care of the reset. The staff will maintain their professional ignorance. You're welcome.",
    ),
}
_SAFE_OUTCOMES = frozenset({
    "failed", "partial", "unverified", "unresolved", "unavailable",
    "action_error", "not_configured", "authentication_failed", "cancelled",
    "unknown", "skipped",
})


def dinner_music_feedback(steps, *, guest=False, visitor_present=False):
    """Describe optional handoff evidence without claiming playback started."""
    music = [step for step in steps
             if evidence_value(step, "target") == "dinner_music" and evidence_value(step, "action") == "request_playback"
             and evidence_value(step, "required") is False]
    if not music:
        return ""
    status: RoutineActionStatus | None
    try:
        status = RoutineActionStatus(evidence_value(music[-1], "status"))
    except (ValueError, TypeError):
        status = None
    if status in {RoutineActionStatus.REQUESTED, RoutineActionStatus.ALREADY_REQUESTED}:
        prefix = "I've requested the music." if status is RoutineActionStatus.REQUESTED else "The music request is already in progress."
        if guest_lines(guest or visitor_present is not False):
            return prefix + " Spotify works on its own timetable and doesn't like to be hurried. Who knows when it'll join the party."
        return prefix + " Spotify works on its own bloody timetable and doesn't like to be hurried, so God knows when it'll join the party."
    return "The lights are set, but I couldn't confirm the music request."


def movie_request_reply(action, *, guest=False, visitor_present=False):
    """Add cinema sass to an accepted request, without claiming completion."""
    action = action if action in _MOVIE_HOME else "toggle"
    prefix = {"start": "Movie setup requested.", "end": "Movie shutdown requested.", "toggle": "Movie Time requested."}[action]
    mode = "guest" if guest_lines(guest or visitor_present is not False) else "home"
    lines = (_MOVIE_GUEST if mode == "guest" else _MOVIE_HOME)[action]
    chosen = household_language.render(ROTATION.choose((mode, "movie", action), lines, topic=topic_for("movie", action), polite=mode == "guest"))
    return prefix + " " + chosen


def morning_request_reply(*, guest=False, visitor_present=False):
    """Greet an accepted morning request without claiming light verification."""
    mode = "guest" if guest_lines(guest or visitor_present is not False) else "home"
    lines = _MORNING_GUEST if mode == "guest" else _MORNING_HOME
    chosen = household_language.render(ROTATION.choose((mode, "morning"), lines, topic=topic_for("morning"), polite=mode == "guest"))
    return "Good morning. " + chosen


def night_request_reply(*, guest=False, visitor_present=False):
    """Acknowledge bedtime without claiming the household has shut down."""
    mode = "guest" if guest_lines(guest or visitor_present is not False) else "home"
    lines = _NIGHT_GUEST if mode == "guest" else _NIGHT_HOME
    chosen = household_language.render(ROTATION.choose((mode, "night"), lines, topic=topic_for("night"), polite=mode == "guest"))
    return "Good night. " + chosen


def sexy_request_reply(action, *, guest=False, visitor_present=False):
    """Acknowledge the request without claiming music or devices are ready."""
    action = "end" if action == "end" else "start"
    mode = "guest" if guest_lines(guest or visitor_present is not False) else "home"
    lines = (_SEXY_GUEST if mode == "guest" else _SEXY_HOME)[action]
    chosen = household_language.render(ROTATION.choose((mode, "sexy", action), lines, topic=topic_for("sexy", action), polite=mode == "guest"))
    return chosen


def response_guest_mode(guest_mode, visitor_present):
    """Keep Guest Mode authority independent of the response persona.

    The persona only switches to guest wording when Settings -> Household ->
    Guest tone is "polite"; the default keeps Declan's Home lines (FUT-60).
    """
    return "on" if guest_lines(guest_mode != "off" or visitor_present is not False) else "off"


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

    Guest authority and visitor presence are independent signals. With the
    polite guest tone, unknown visitor state is treated as private; with the
    default Home tone guests hear the same roasts as the household (FUT-60).
    """
    if not isinstance(reply, str) or (not reply.strip() and category != "dinner"):
        return reply
    # Unknown and future outcomes must never be treated as verified success.
    # This is deliberately an allowlist, not a denylist of known failures.
    if safety or parse_outcome(outcome) is not Outcome.CONFIRMED or already_decorated:
        return reply
    # Replies can arrive pre-decorated from a handler. Do not append a second
    # roast, including when the handler used a different personality category.
    if any(household_language.render(line) in reply
           for line in (*_SAVAGE, *_GUEST, *_DINNER_HOME, *_DINNER_GUEST)):
        return reply
    lines: tuple[str, ...]
    if guest_lines(guest or visitor_present is not False):
        lines = _DINNER_GUEST if category == "dinner" else _GUEST
        key = ("guest", category)
    else:
        lines = _DINNER_HOME if category == "dinner" else _SAVAGE
        key = ("home", category)
    chosen = household_language.render(ROTATION.choose(
        key, lines, topic=topic_for("dinner" if category == "dinner" else category, "general"),
        polite=key[0] == "guest"))
    return (reply.rstrip() + " " if reply.strip() else "") + chosen

