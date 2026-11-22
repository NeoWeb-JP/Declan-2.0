"""Who's home (FUT-30, #834).

"Is Edd home?", "is Jaco back yet?", "has Edd left?", "who's home?",
"is anyone in?". Answers come from Home Assistant ``person`` entities (their
phones), so they never depend on speaker recognition.

- Only home or out. Zone names ("work", "the gym") are never said: knowing
  where someone is goes beyond what the household asked for.
- A person whose phone isn't reporting (``unknown`` / ``unavailable``) is
  "I can't tell", never guessed.
- Hidden in Guest mode (or when Guest mode can't be read).
- A name that isn't a person in Home Assistant returns None, so "is the
  washing in?" is left to the rest of Declan.
"""
import re

from declan.core.execution_results import ExecutionResult, Outcome
from declan.ha import ha_reads

_TEMPLATE = (
    "{% set ns = namespace(people=[]) %}"
    "{% for person in states.person %}"
    "{% set ns.people = ns.people + [[person.entity_id, person.state, person.name]] %}"
    "{% endfor %}{{ ns.people | to_json }}"
)
_UNKNOWN = frozenset({"unknown", "unavailable", ""})
_NAME = r"[a-z][a-z' -]{0,30}?"
_ALL = re.compile(r"who(?:'s| is| are)(?: at)? (?:home|in|back|in the house)(?: (?:now|yet|right now|at the moment))?"
                  r"|who(?:'s| is) (?:not |out|away)(?: home)?")
_ANYONE = re.compile(r"(?:is|are) (?:anyone|anybody|someone|somebody|there anyone|there anybody) (?:home|in|at home|in the house)"
                     r"|is the house empty|is (?:everyone|everybody) (?:home|in|out|back)")
_ONE = re.compile(rf"(?:is|are) (?P<name>{_NAME}) (?:at home|home|in|back|back home|out|away)(?: (?:yet|now|already|right now))?"
                  rf"|(?:has|did) (?P<other>{_NAME}) (?:left|gone out|got home|gotten home|come home|get home|come back|got back|arrived)"
                  r"(?: (?:yet|already))?")

GUEST_LINES = (
    "Nice try. I don't do headcounts for visitors.",
    "Who's home is household business, my bru.",
    "Ask your host. I'm a butler, not a doorman.",
)
GUEST_TOPIC = "refusing to tell a guest who in the household is home (never say who)"


def match(phrase):
    """("all",) | ("anyone",) | ("one", name) | None."""
    if not isinstance(phrase, str):
        return None
    text = " ".join(phrase.casefold().replace("’", "'").split()).strip(" ?.!")
    text = re.sub(r"^(?:declan,? |hey declan,? |howzit declan,? )", "", text)
    text = re.sub(r",? declan$", "", text)
    if _ALL.fullmatch(text):
        return ("all",)
    if _ANYONE.fullmatch(text):
        return ("anyone",) if not text.startswith("is everyone") and not text.startswith("is everybody") else ("all",)
    if found := _ONE.fullmatch(text):
        name = (found["name"] or found["other"] or "").strip()
        name = re.sub(r"^the ", "", name)
        if name in {"it", "that", "this", "the light", "the lights", "the music", "the tv", "dinner", "the washing"}:
            return None
        return ("one", name) if name else None
    return None


def people(connection):
    rows = ha_reads.template(connection, _TEMPLATE)
    if not isinstance(rows, list):
        raise ValueError("Home Assistant didn't list people.")
    return [{"entity_id": row[0], "state": row[1], "name": row[2]} for row in rows
            if isinstance(row, list) and len(row) == 3 and all(isinstance(value, str) for value in row)]


def _norm(text):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.casefold().replace("'s", "")).split())


def find(name, rows):
    """The person row for a spoken name: full name, first name or entity id."""
    wanted = _norm(name)
    for row in rows:
        full = _norm(row["name"])
        object_id = _norm(row["entity_id"].split(".", 1)[-1].replace("_", " "))
        if wanted in {full, object_id} or (full and wanted == full.split()[0]):
            return row
    return None


def _list(names):
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _guest_line():
    from declan.turn import line_freshness
    return line_freshness.pick("presence:guest", GUEST_LINES, topic=GUEST_TOPIC)


def result(request, connection, *, guest):
    if request is None:
        return None
    if guest:
        return ExecutionResult(_guest_line(), Outcome.REJECTED)
    if connection is None:
        return ExecutionResult("The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED)
    try:
        rows = people(connection)
    except (OSError, ValueError, TypeError):
        return ExecutionResult("I couldn't ask Home Assistant who's home.", Outcome.UNAVAILABLE)
    if request[0] == "one":
        row = find(request[1], rows)
        if row is None:
            return None  # not a person ("is the washing in?"): let the rest of Declan answer
        name = row["name"] or request[1].title()
        if row["state"] in _UNKNOWN:
            return ExecutionResult(f"I can't tell. {name}'s phone isn't reporting to Home Assistant.", Outcome.UNAVAILABLE)
        if row["state"] == "home":
            return ExecutionResult(f"Yes, {name}'s home.", Outcome.CHAT_ANSWER)
        return ExecutionResult(f"No, {name}'s out.", Outcome.CHAT_ANSWER)
    if not rows:
        return ExecutionResult("Home Assistant doesn't have any people set up, so I can't tell.", Outcome.NOT_CONFIGURED)
    home = [row["name"] for row in rows if row["state"] == "home"]
    unknown = [row["name"] for row in rows if row["state"] in _UNKNOWN]
    tail = f" I can't tell about {_list(unknown)}." if unknown else ""
    if request[0] == "anyone":
        reply = f"Yes: {_list(home)}." if home else "No, nobody's home."
        return ExecutionResult(reply + tail, Outcome.CHAT_ANSWER)
    if not home:
        reply = "Nobody's home. Just me, talking to myself."
    elif len(home) == len(rows):
        reply = "Everyone's home." if len(home) > 1 else f"Just {home[0]}."
    else:
        reply = f"Just {home[0]}." if len(home) == 1 else f"{_list(home)} are home."
    return ExecutionResult(reply + tail, Outcome.CHAT_ANSWER)
