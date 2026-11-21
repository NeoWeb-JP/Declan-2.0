"""'Where did I put...?' (FUT-42, #834). Edd is always losing things.

"Declan, the spare car key is in the hall drawer." ... "Where's the spare car
key?" -> "Filed. Unlike everything else around here. Hall drawer, since Tuesday."

- Local only (SQLite), nothing goes to the AI.
- Shared by the household; it doesn't depend on who's speaking.
- Saying a new place replaces the old one; "forget the car key" removes it.
- Fuzzy matching: "car key" finds "spare car key"; a slight mishearing still matches.
- Guests get a cheeky refusal and no location, and can't save things (owner's lines).
- The household joke always comes first and the answer straight after, never instead.

Explicit sentences ("I put the passports in the safe", "where did I leave my
glasses?") are recognised before other commands. A bare statement ("the key is
in the drawer") only after nothing else understood it, so "the lights are on in
the kitchen" never gets filed.
"""
import difflib
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from time import time

PATH = Path(__file__).resolve().parents[2] / ".data" / "whereabouts.sqlite3"
MAX_ITEMS = 500
_PLACE_WORDS = r"(?:in|on|under|underneath|behind|inside|next to|beside|by|at|on top of|in front of|between|with)"
_ARTICLE = r"(?:the |my |our |his |her |their |a |an )?"
_ITEM = r"(?P<item>[a-z][a-z0-9' -]{0,60}?)"
_PLACE = rf"(?P<place>{_PLACE_WORDS} [a-z0-9' ,-]{{2,80}})"

_EXPLICIT_SAVE = (
    re.compile(rf"(?:remember (?:that )?)?(?:i|we|edd|ed|jaco)(?:'ve| have| has)? (?:put|left|moved|stashed|hidden|hid|stored|kept|placed) {_ARTICLE}{_ITEM} {_PLACE}"),
    re.compile(rf"remember (?:that )?{_ARTICLE}{_ITEM} (?:is|are|'s) (?:now )?{_PLACE}"),
    re.compile(rf"{_ARTICLE}{_ITEM} (?:is|are|'s) (?:now )?(?:kept |stored )?{_PLACE}(?:,? (?:remember|remember that|for next time))"),
)
_BARE_SAVE = re.compile(rf"{_ARTICLE}{_ITEM} (?:is|are|'s|'re) (?:now )?(?:kept |stored )?{_PLACE}")
_PERSONAL_QUESTIONS = (
    re.compile(rf"where (?:did|have) (?:i|we|edd|ed|jaco|you) (?:put|left|leave|stash|stashed|hide|hidden|store|stored|keep|kept|move|moved) {_ARTICLE}{_ITEM}"),
    re.compile(rf"(?:have|has) (?:you|anyone|anybody) seen {_ARTICLE}{_ITEM}"),
    re.compile(rf"do you know where {_ARTICLE}{_ITEM} (?:is|are)"),
    re.compile(rf"where(?: is|'s| are|'re) (?:my|our|edd's|ed's|jaco's) {_ITEM}"),
)
_QUESTION = re.compile(rf"where(?: is|'s| are|'re) (?:the )?{_ITEM}")
_LIST = re.compile(r"what (?:have (?:i|we) told you about|things do you know where they are|are you keeping track of)|"
                   r"(?:list|what are) the things (?:you know|i've told you about)")
_FORGET = re.compile(rf"forget (?:about |where )?{_ARTICLE}{_ITEM}(?: is| are)?")
# Things that look like statements but are commands or chatter.
_NOT_ITEMS = frozenset({"lights", "light", "music", "tv", "television", "it", "that", "this", "he", "she", "they",
                        "dinner", "food", "the time", "heating", "fan", "everyone", "everybody", "nobody", "someone"})

GUEST_LINES = (
    "Wouldn't you like to know.",
    "If I told you, I'd have to have you killed.",
    "You expect me to remember that in this mess of tangled wires and circuits?",
)
LINES = {
    "save": ("Noted. I'll be the only one in this house who knows where anything is.",
             "Filed. Unlike everything else around here."),
    "found": ("Lucky for you, one of us pays attention.",
              "Here's a novel idea, boet: put things back."),
    "again": ("Again? I'm starting a lost property office.",),
    "not_found": ("No idea, my bru. You never told me, and I don't have hands to look.",),
    "guest": GUEST_LINES,
}
TOPICS = {
    "save": "after noting where someone put something, so they can find it later",
    "found": "a cheeky remark before telling someone where they left their thing",
    "again": "someone asking where the same thing is for the second time today",
    "not_found": "you don't know where their thing is because nobody told you",
    "guest": "refusing to tell a guest where the household keeps something (never say where)",
}


def _connect(path=None):
    path = Path(PATH if path is None else path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    db.execute("CREATE TABLE IF NOT EXISTS items (key TEXT PRIMARY KEY, item TEXT NOT NULL, place TEXT NOT NULL, "
               "saved_at REAL NOT NULL, asked_at REAL)")
    return db


def _clean(text):
    return " ".join(text.casefold().replace("’", "'").split()).strip(" ?.!,")


def key_for(item):
    words = [word for word in re.sub(r"[^a-z0-9 ]", " ", item.casefold()).split()
             if word not in {"the", "my", "our", "a", "an", "his", "her", "their", "some"}]
    # Singular-ish, so "keys" finds "key".
    return " ".join(word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word
                    for word in words)


def _item_ok(item):
    item = item.strip()
    return bool(item) and item not in _NOT_ITEMS and key_for(item) not in _NOT_ITEMS and len(item.split()) <= 6


def match(text):
    """(kind, payload, explicit) or None. kind: save, find, list, forget."""
    if not isinstance(text, str):
        return None
    text = re.sub(r"^(?:(?:hey|ok|okay|howzit) )?declan,? ", "", _clean(text))
    # "moved the passports to the safe" -> "... in the safe"
    text = re.sub(r"\b(moved|put|stashed|hid|taken|took) (.+?) (?:to|into) (?=(?:the|my|our) )", r"\1 \2 in ", text)
    if _LIST.fullmatch(text):
        return ("list", None, True)
    forget = _FORGET.fullmatch(text)
    if forget and _item_ok(forget["item"]):
        return ("forget", forget["item"].strip(), True)
    for pattern in _EXPLICIT_SAVE:
        found = pattern.fullmatch(text)
        if found and _item_ok(found["item"]):
            return ("save", (found["item"].strip(), found["place"].strip()), True)
    for pattern in _PERSONAL_QUESTIONS:
        personal = pattern.fullmatch(text)
        if personal and _item_ok(personal["item"]):
            return ("find", (personal["item"].strip(), True), True)
    question = _QUESTION.fullmatch(text)
    if question and _item_ok(question["item"]):
        # "Where is Peru?" falls through when nothing is filed under that name.
        return ("find", (question["item"].strip(), False), True)
    bare = _BARE_SAVE.fullmatch(text)
    if bare and _item_ok(bare["item"]):
        return ("save", (bare["item"].strip(), bare["place"].strip()), False)
    return None


def save(item, place, *, now=None, path=None):
    now = time() if now is None else now
    with closing(_connect(path)) as db, db:
        if db.execute("SELECT COUNT(*) FROM items").fetchone()[0] >= MAX_ITEMS and not db.execute(
                "SELECT 1 FROM items WHERE key = ?", (key_for(item),)).fetchone():
            raise ValueError("I'm keeping track of too many things. Forget a few first.")
        previous = db.execute("SELECT place FROM items WHERE key = ?", (key_for(item),)).fetchone()
        db.execute("INSERT INTO items VALUES (?, ?, ?, ?, NULL) ON CONFLICT(key) DO UPDATE SET "
                   "item = excluded.item, place = excluded.place, saved_at = excluded.saved_at, asked_at = NULL",
                   (key_for(item), item, place, now))
    return previous[0] if previous else None


def find(item, *, path=None):
    """The best stored match: exact, then word containment, then a close spelling."""
    wanted = key_for(item)
    if not wanted:
        return None
    with closing(_connect(path)) as db:
        rows = db.execute("SELECT key, item, place, saved_at, asked_at FROM items").fetchall()
    exact = [row for row in rows if row[0] == wanted]
    if exact:
        return exact[0]
    words = set(wanted.split())
    containing = [row for row in rows if words <= set(row[0].split()) or set(row[0].split()) <= words]
    if len(containing) == 1:
        return containing[0]
    close = difflib.get_close_matches(wanted, [row[0] for row in rows], n=1, cutoff=0.8)
    return next((row for row in rows if row[0] == close[0]), None) if close else None


def mark_asked(key, *, now=None, path=None):
    with closing(_connect(path)) as db, db:
        db.execute("UPDATE items SET asked_at = ? WHERE key = ?", (time() if now is None else now, key))


def forget(item, *, path=None):
    row = find(item, path=path)
    if row is None:
        return None
    with closing(_connect(path)) as db, db:
        db.execute("DELETE FROM items WHERE key = ?", (row[0],))
    return row[1]


def listing(*, path=None):
    with closing(_connect(path)) as db:
        rows = db.execute("SELECT item, place, saved_at FROM items ORDER BY saved_at DESC").fetchall()
    return [{"item": item, "place": place, "saved_at": saved_at} for item, place, saved_at in rows]


def _local(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).astimezone()


def since(saved_at, now=None):
    now_time = _local(time() if now is None else now)
    then = _local(saved_at)
    days = (now_time.date() - then.date()).days
    if days <= 0:
        return "since earlier today"
    if days == 1:
        return "since yesterday"
    if days < 7:
        return f"since {then:%A}"
    return f"since {then.day} {then:%B}"


def _line(kind, polite=False):
    from declan.turn import line_freshness
    return line_freshness.pick("where:" + kind, LINES[kind], topic=TOPICS[kind], polite=polite)


def _place(place):
    place = place.strip(" .")
    return place[:1].upper() + place[1:] + "."


def answer(request, *, guest=False, now=None, path=None):
    """Spoken reply, or None to let another part of Declan answer ("where is Peru?")."""
    kind, payload, _ = request
    now = time() if now is None else now
    if guest:
        return _line("guest", polite=False) if kind in {"save", "find", "list", "forget"} else None
    if kind == "list":
        rows = listing(path=path)
        if not rows:
            return "Nobody's told me where anything is. Typical."
        names = [row["item"] for row in rows[:8]]
        more = f" and {len(rows) - 8} more" if len(rows) > 8 else ""
        return "I know where these are: " + ", ".join(names) + more + "."
    if kind == "forget":
        removed = forget(payload, path=path)
        return f"Forgotten: {removed}. Good luck finding it now." if removed else f"I didn't know where {payload} was anyway."
    if kind == "save":
        item, place = payload
        previous = save(item, place, now=now, path=path)
        moved = f" Moved from {previous.removeprefix('in ').removeprefix('on ')}." if previous and previous != place else ""
        return f"{_line('save')} {item[:1].upper() + item[1:]}: {place}.{moved}"
    item, personal = payload
    row = find(item, path=path)
    if row is None:
        return f"{_line('not_found')}" if personal else None
    key, _name, place, saved_at, asked_at = row
    asked_today = asked_at is not None and _local(asked_at).date() == _local(now).date()
    mark_asked(key, now=now, path=path)
    joke = _line("again" if asked_today else "found")
    return f"{joke} {_place(place)[:-1]}, {since(saved_at, now)}."
