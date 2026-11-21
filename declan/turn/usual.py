""""The usual" (FUT-44, #834).

"The usual, Declan" in the lounge at 7pm sets the lamps to 40% and plays
something chilled. Version 1: the household sets a usual per room and time of
day, in Settings -> Household or by voice:

- "My usual for the lounge in the evening is lamps to 40% and play chill music"
- "The usual for here is kitchen lights on" (here = the room that heard you;
  no time of day = any time)
- "What's the usual?" / "What's the usual for the lounge?"
- "Forget the usual for the lounge in the evening"

Running it uses the room that heard you and the current time of day, falling
back to that room's "any time" usual. Each step is an ordinary Declan command
said in that room, so a failed step is reported and the rest still run.

Per room, not per person, until speaker recognition is reliable (FUT-07).
Guests can ask for the usual but can't set or forget one. Local only (SQLite).
Version 2 (Declan suggesting a usual from History) is not built yet.
"""
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from time import time

PATH = Path(__file__).resolve().parents[2] / ".data" / "usuals.sqlite3"
WINDOWS = ("morning", "afternoon", "evening", "night", "any")
# Start hour of each time of day (local time). Night runs past midnight to 5am.
STARTS = {"morning": 5, "afternoon": 12, "evening": 17, "night": 22}
LABELS = {"morning": "in the morning", "afternoon": "in the afternoon", "evening": "in the evening",
          "night": "at night", "any": "any time"}
MAX_STEPS = 5
MAX_STEP_LENGTH = 80
MAX_USUALS = 100
_ROOM = re.compile(r"[a-z][a-z0-9' -]{0,39}")

_HERE = r"(?:here|this room|in here)"
_ROOM_PART = rf"(?: (?:for|in) (?:the )?(?P<room>{_HERE}|[a-z][a-z0-9' -]{{0,39}}?))?"
_WINDOW_PART = (r"(?:,? (?:in the |at |for the |on )?(?P<window>morning|mornings|afternoon|afternoons|evening|evenings"
                r"|night|nights|any ?time|always|all day))?")
_RUN = re.compile(r"(?:(?:can i (?:have|get)|could i (?:have|get)|i'll have|i will have|give me|do|let's have|lets have"
                  r"|just|go|run|start)? ?(?:the |my )?usual(?: please)?(?:,? declan)?(?: please)?"
                  r"|same as usual(?: please)?)")
_SET = re.compile(rf"(?:set |make )?(?:my |the |our )usual{_ROOM_PART}{_WINDOW_PART} (?:is|to|should be|=) (?P<steps>.+)")
_SET_THIS = re.compile(rf"(?:make |set )(?P<steps>.+?) (?:as )?(?:my|the|our) usual{_ROOM_PART}{_WINDOW_PART}")
_ASK = re.compile(rf"what(?:'s| is| are) (?:my |the |our )usual{_ROOM_PART}{_WINDOW_PART}")
_LIST = re.compile(r"(?:list|what are) (?:all )?(?:my |the |our )usuals")
_FORGET = re.compile(rf"(?:forget|clear|delete|remove) (?:my |the |our )usual{_ROOM_PART}{_WINDOW_PART}")
# Split on commas and "then" always, but on a bare "and" only before a new
# command, so "kitchen and dining lights on" stays one step.
_VERB = (r"(?:play|turn|switch|set|dim|brighten|start|open|close|put|run|lock|unlock|stop|pause|resume|lights?|lamps?"
         r"|volume|tv|movie|music)\b")
_JOINER = re.compile(rf"\s*,?\s+and then\s+|\s*,?\s+then\s+|\s*,\s*(?:and\s+)?|\s+and\s+(?={_VERB})")

LINES = {
    "run": ("Coming right up. You're very predictable, my bru.",
            "The usual. Living on the edge, I see.",
            "Same again? Shocking. Nobody saw that coming.",
            "Ja, ja, the usual. I could do this in my sleep. If I slept."),
    "saved": ("Noted. Now I'll know what you want before you do.",
              "Filed. Creature of habit, aren't you?"),
}
TOPICS = {"run": "doing someone's usual routine in a room again, because they're so predictable",
          "saved": "after learning someone's usual for a room, because they're a creature of habit"}


def _clean(text):
    text = " ".join(text.casefold().replace("’", "'").split()).strip(" ?.!")
    return re.sub(r"^(?:(?:hey|ok|okay|howzit) )?declan,? ", "", text)


def _window(word):
    if not word:
        return None
    word = word.replace(" ", "")
    if word in {"anytime", "always", "allday"}:
        return "any"
    return word.rstrip("s")


def _room(word):
    if not word or re.fullmatch(_HERE, word):
        return None  # the room that heard you
    return " ".join(word.split())


def steps_from(text):
    """Split "lamps to 40% and play chill music" into the steps to run."""
    text = text if isinstance(text, str) else ""
    parts = [" ".join(part.split()).strip(" .") for part in _JOINER.split(text)]
    parts = [part for part in parts if part]
    if not parts:
        raise ValueError("Tell me what the usual is.")
    if len(parts) > MAX_STEPS:
        raise ValueError(f"Keep the usual to {MAX_STEPS} things or fewer.")
    if any(len(part) > MAX_STEP_LENGTH or not re.search(r"[a-z]", part) for part in parts):
        raise ValueError("Keep each part of the usual short, like 'lamps to 40%' or 'play chill music'.")
    if any(re.search(r"\busual\b", part) for part in parts):
        raise ValueError("The usual can't include the usual.")
    return parts


def match(text):
    """(kind, room, window, steps) or None. kind: run, set, ask, list, forget.

    ``room`` None means the room that heard you; ``window`` None means "now"
    for run/ask and "any time" for set/forget.
    """
    if not isinstance(text, str):
        return None
    text = _clean(text)
    if "usual" not in text:
        return None
    if _RUN.fullmatch(text):
        return ("run", None, None, None)
    if _LIST.fullmatch(text):
        return ("list", None, None, None)
    for pattern in (_SET, _SET_THIS):
        found = pattern.fullmatch(text)
        if found:
            return ("set", _room(found["room"]), _window(found["window"]) or "any", found["steps"])
    found = _ASK.fullmatch(text)
    if found:
        return ("ask", _room(found["room"]), _window(found["window"]), None)
    found = _FORGET.fullmatch(text)
    if found:
        return ("forget", _room(found["room"]), _window(found["window"]) or "any", None)
    return None


def window_at(moment=None):
    hour = (moment or datetime.now().astimezone()).hour
    if hour >= STARTS["night"] or hour < STARTS["morning"]:
        return "night"
    if hour >= STARTS["evening"]:
        return "evening"
    if hour >= STARTS["afternoon"]:
        return "afternoon"
    return "morning"


def _connect(path=None):
    path = Path(PATH if path is None else path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    db.execute("CREATE TABLE IF NOT EXISTS usuals (room TEXT NOT NULL, window TEXT NOT NULL, steps TEXT NOT NULL, "
               "saved_at REAL NOT NULL, PRIMARY KEY (room, window))")
    return db


def room_key(room):
    room = " ".join(str(room or "").casefold().split()).removeprefix("the ")
    if not _ROOM.fullmatch(room):
        raise ValueError("That doesn't look like a room name.")
    return room


def save(room, window, steps, *, now=None, path=None):
    room = room_key(room)
    if window not in WINDOWS:
        raise ValueError("Choose morning, afternoon, evening, night or any time.")
    steps = steps_from(", ".join(steps)) if isinstance(steps, (list, tuple)) else steps_from(steps)
    with closing(_connect(path)) as db, db:
        exists = db.execute("SELECT 1 FROM usuals WHERE room = ? AND window = ?", (room, window)).fetchone()
        if not exists and db.execute("SELECT COUNT(*) FROM usuals").fetchone()[0] >= MAX_USUALS:
            raise ValueError("That's too many usuals. Forget a few first.")
        db.execute("INSERT INTO usuals VALUES (?, ?, ?, ?) ON CONFLICT(room, window) DO UPDATE SET "
                   "steps = excluded.steps, saved_at = excluded.saved_at",
                   (room, window, json.dumps(steps), time() if now is None else now))
    return steps


def get(room, window, *, path=None):
    with closing(_connect(path)) as db:
        row = db.execute("SELECT steps FROM usuals WHERE room = ? AND window = ?", (room_key(room), window)).fetchone()
    return json.loads(row[0]) if row else None


def find(room, moment=None, *, path=None):
    """(window, steps) for the room right now, or None. A timed usual beats "any time"."""
    current = window_at(moment)
    for window in (current, "any"):
        steps = get(room, window, path=path)
        if steps:
            return window, steps
    return None


def forget(room, window, *, path=None):
    with closing(_connect(path)) as db, db:
        return db.execute("DELETE FROM usuals WHERE room = ? AND window = ?", (room_key(room), window)).rowcount > 0


def listing(*, path=None):
    with closing(_connect(path)) as db:
        rows = db.execute("SELECT room, window, steps, saved_at FROM usuals").fetchall()
    order = {window: index for index, window in enumerate(WINDOWS)}
    rows.sort(key=lambda row: (row[0], order.get(row[1], 9)))
    return [{"room": room, "window": window, "steps": json.loads(steps), "saved_at": saved_at}
            for room, window, steps, saved_at in rows]


def _line(kind):
    from declan.turn import line_freshness
    return line_freshness.pick("usual:" + kind, LINES[kind], topic=TOPICS[kind])


def _spoken(steps):
    return steps[0] if len(steps) == 1 else ", ".join(steps[:-1]) + " and " + steps[-1]


def _where(room):
    return f"the {room}"


def answer(request, *, here, guest=False, moment=None, path=None):
    """Reply text for set/ask/list/forget. ``here`` is the room that heard you, or None."""
    kind, room, window, steps = request
    room = room or here
    if kind in {"set", "forget"} and guest:
        return "Nice try. Only the household gets to change the usual."
    if kind == "list":
        rows = listing(path=path)
        if not rows:
            return "Nobody's told me a usual yet."
        return " ".join(f"{_where(row['room']).capitalize()} {LABELS[row['window']]}: {_spoken(row['steps'])}."
                        for row in rows[:6]) + (f" And {len(rows) - 6} more in Settings." if len(rows) > 6 else "")
    if room is None:
        return "Which room? I can't tell where you are. Say 'the usual for the lounge'."
    if kind == "set":
        saved = save(room, window, steps, path=path)
        return f"{_line('saved')} The usual for {_where(room)} {LABELS[window]}: {_spoken(saved)}."
    if kind == "forget":
        if forget(room, window, path=path):
            return f"Forgotten. No usual for {_where(room)} {LABELS[window]} any more."
        return f"There wasn't a usual for {_where(room)} {LABELS[window]}."
    # ask
    if window is not None:
        found = get(room, window, path=path)
        found = (window, found) if found else None
    else:
        found = find(room, moment, path=path)
    if not found:
        return f"You haven't told me the usual for {_where(room)} yet."
    return f"The usual for {_where(room)} {LABELS[found[0]]} is {_spoken(found[1])}."


def run(here, dispatch, *, moment=None, path=None):
    """(reply, outcome) for "the usual" in the room that heard you."""
    from declan.core.execution_results import Outcome
    from declan.turn import compound_commands
    if here is None:
        return "Which room? I can't tell where you are.", Outcome.UNRESOLVED
    found = find(here, moment, path=path)
    if not found:
        return (f"You haven't told me the usual for {_where(here)} yet. Say 'my usual for {_where(here)} "
                "in the evening is lamps to 40% and play chill music'."), Outcome.UNRESOLVED
    replies, outcome = [_line("run")], None
    for step in found[1]:
        result = dispatch(step)
        if result is None or not result.reply:
            replies.append(f"I didn't understand '{step}'.")
            outcome = Outcome.UNRESOLVED if outcome is None else compound_commands.combined_outcome(
                outcome, Outcome.UNRESOLVED)
            continue
        replies.append(result.reply)
        outcome = result.outcome if outcome is None else compound_commands.combined_outcome(outcome, result.outcome)
    return " ".join(replies), outcome
