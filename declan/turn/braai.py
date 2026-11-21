"""Braai master (FUT-43, #834).

"Declan, braai time" plays the Braai playlist in the room you're in, turns on
the garden lights and checks for rain, with braai sass on top. Each part is an
ordinary Declan command, so a part that fails says so and the rest still runs.
Several named timers in one go ("boerewors 12 minutes, chops 8 minutes") use
the cooking-timer splitter; "how long on the chops?" asks the chops timer.
"Braai's over" gets the closing line; the music keeps playing until you stop it.

Lines: the owner's three, plus the approved extras (21 Nov 2026). They rest and
get topped up like all sass (FUT-61).
"""
import re

START = re.compile(r"(?:it's |its |let's |lets |start (?:the |a )?|time for (?:a |the )?)?braai(?: time| mode)?(?: time)?"
                   r"|(?:we're |we are )having a braai|fire up the braai|light the braai")
END = re.compile(r"(?:the )?braai(?:'s| is) (?:over|done|finished)|(?:end|stop|finish) (?:the )?braai(?: mode| time)?")
HOW_LONG = re.compile(r"how long (?:left |is left |to go )?(?:on|for) (?:the )?(?P<name>[a-z][a-z ]{1,40}?)(?: timer)?")

LINES = {
    "start": (
        "Oh great, I'm going to smell like smoke for weeks.",
        "Don't burn down the neighbour's fence.",
        "I'm going to have fatty boerewors fingerprints all over my screens. Who's cleaning up that shit?",
        "Another braai? The neighbours are going to start charging rent for the smoke.",
        "Garden lights on. Please keep the fire on the braai and off me.",
    ),
    "end": ("Braai's over. I'll be airing out my circuits until Thursday.",
            "Braai's done. Somebody scrape the grid before it becomes a science project."),
    "rain": ("I'm told a true South African braais anyway.",),
}
TOPICS = {"start": "starting a South African braai (barbecue) at home: smoke, boerewors, chops, the neighbours",
          "end": "the braai is over and everyone's full", "rain": "rain is forecast but they're braaing anyway"}
STEPS = ("play braai music", "turn on the garden lights", "will it rain today")


def match(phrase):
    if not isinstance(phrase, str):
        return None
    text = " ".join(phrase.casefold().replace("’", "'").split()).strip(" ?.!")
    if START.fullmatch(text):
        return "start"
    if END.fullmatch(text):
        return "end"
    return None


def how_long(phrase):
    """"how long on the chops?" -> the timer query Declan already understands."""
    found = HOW_LONG.fullmatch(" ".join(phrase.casefold().split()).strip(" ?.!")) if isinstance(phrase, str) else None
    return f"how much time is left on the {found['name'].strip()} timer" if found else None


def line(kind, polite=False):
    from declan.turn import line_freshness
    return line_freshness.pick("braai:" + kind, LINES[kind], topic=TOPICS[kind], polite=polite)


def run(kind, dispatch):
    """(reply, outcome) using ``dispatch(phrase)`` for each part."""
    from declan.turn import compound_commands
    if kind == "end":
        # A plain "stop" is household-wide, so the braai's end never stops music by itself.
        from declan.core.execution_results import Outcome
        return line("end"), Outcome.CHAT_ANSWER
    replies, outcome = [line("start")], None
    for phrase in STEPS:
        result = dispatch(phrase)
        if result is None or not result.reply:
            continue
        reply = result.reply
        if phrase.startswith("will it rain") and re.search(r"\brain", reply, re.IGNORECASE) and not re.search(
                r"\b(?:no|not|dry|0 ?%)\b", reply, re.IGNORECASE):
            reply += " " + line("rain")
        replies.append(reply)
        if not phrase.startswith("will it rain"):
            outcome = result.outcome if outcome is None else compound_commands.combined_outcome(outcome, result.outcome)
    return " ".join(replies), outcome
