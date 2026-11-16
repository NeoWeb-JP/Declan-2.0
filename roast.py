"""On-demand, light-hearted roasts; never change household state."""
import re
from random import SystemRandom

_RANDOM = SystemRandom()
_NAME = re.compile(r"[a-z][a-z '\\-]{0,39}", re.I)
_REQUEST = re.compile(r"(?:please )?roast(?: (?:me|myself|[a-z][a-z '\\-]{0,39}))?", re.I)

HOME = (
    "{name}, you have the confidence of someone who's never read the error log.",
    "{name}, if procrastination were a smart-home integration, you'd still be configuring it.",
    "{name}, you're living proof that turning it off and on again doesn't fix everything.",
    "{name}, your plans have more unfinished steps than a Home Assistant automation.",
    "{name}, even Tux looks at your decisions and thinks, 'Bit ambitious, mate.'",
)
GUEST = (
    "{name}, you've got main-character energy and supporting-cast organisation.",
    "{name}, you bring a special kind of chaos to a perfectly ordinary Tuesday.",
    "{name}, if enthusiasm were a qualification, you'd be dangerously overqualified.",
    "{name}, your confidence is impressive. Your planning is more of a suggestion.",
    "{name}, even Tux has questions about your leadership style.",
)


def target(phrase):
    """Return a validated name, or None when this is not a roast command."""
    phrase = phrase.strip().casefold().replace("’", "'")
    if phrase in {"roast me", "roast myself", "please roast me"}:
        return "you"
    match = re.fullmatch(r"(?:please )?roast ([a-z][a-z '\\-]{0,39})", phrase)
    if not match:
        return None
    name = match[1].strip()
    if name in {"someone", "anyone"}:
        return None
    return name.title()


def respond(name, *, guest):
    """Guest Mode keeps the roast playful; Home Mode is cheekier."""
    line = _RANDOM.choice(GUEST if guest else HOME)
    if name == "you":
        return line.format(name="My bru")
    return line.format(name=name)
