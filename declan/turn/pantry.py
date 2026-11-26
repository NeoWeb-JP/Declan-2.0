"""Pantry by voice (FUT-76, #834). Barcode scanning was too slow, so you just say it.

"We've got 6 tins of chopped tomatoes", "I've used a tin of chopped tomatoes",
"we're out of rice", "we're running low on coffee", "do we have pasta?",
"how many tins of tomatoes have we got?", "keep at least 4 tins of tomatoes",
"what's running low?", "stop counting rice".

- Stock lives here, locally (SQLite). Nothing goes to the AI, no recipe app needed.
- When something drops below its minimum, runs out or is "running low", it goes on
  the household's shopping list: the Home Assistant to-do list chosen in
  Settings -> Household (for example the shared iPhone Reminders list, synced into
  HA by the Home Assistant iPhone app). It isn't added twice.
- Shared by the household; it doesn't depend on who's speaking. Guests can say
  they've used or run out of something, but can't change counts or minimums.
- The joke comes first and the answer straight after, never instead of it.
"""
import difflib
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from time import time

PATH = Path(__file__).resolve().parents[2] / ".data" / "pantry.sqlite3"
MAX_ITEMS = 300
MAX_COUNT = 999
_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
          "a couple of": 2, "a couple": 2, "a few": 3, "a dozen": 12, "dozen": 12}
_NUMBER = r"(?P<count>\d{1,3}|a couple of|a couple|a few|a dozen|an|a|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty)"
_UNITS = ("tins", "tin", "cans", "can", "bags", "bag", "packs", "pack", "packets", "packet", "jars", "jar",
          "bottles", "bottle", "boxes", "box", "cartons", "carton", "bars", "bar", "rolls", "roll", "loaves",
          "loaf", "bunches", "bunch", "tubs", "tub", "pots", "pot", "sachets", "sachet", "kilos", "kilo", "kg",
          "litres", "litre", "pints", "pint", "dozen")
_UNIT = r"(?:(?P<unit>" + "|".join(_UNITS) + r") (?:of )?)?"
_ITEM = r"(?P<item>[a-z][a-z0-9' -]{1,50}?)"
_WHERE = r"(?: (?:in|into|to) the (?:pantry|cupboard|cupboards|freezer|fridge|larder|store ?room))?"
_WHO = r"(?:(?:i|we|edd|ed|jaco)(?:'ve| have| has)? )?(?:just )?"
_PANTRY = r"(?:pantry|cupboard|cupboards|larder|stock)"

_USED = re.compile(rf"{_WHO}(?P<verb>used|finished|opened)(?P<up> up)? "
                   rf"(?:(?P<last>the last|our last|my last) )?(?:{_NUMBER} )?{_UNIT}(?:the |our |my |some )?{_ITEM}{_WHERE}")
_OUT = re.compile(rf"(?:(?:we're|we are|i'm|i am|we've|we have|we|i've|i have) )?(?:run |ran |completely |totally )?"
                  rf"out of {_ITEM}|there(?:'s| is) no (?:more )?{_ITEM.replace('<item>', '<item2>')} left|"
                  rf"no (?:more )?{_ITEM.replace('<item>', '<item3>')} left")
_LOW = re.compile(rf"(?:(?:we're|we are|i'm|i am) )?(?:running |getting )low on {_ITEM}")
_STOCK = re.compile(rf"(?:we've got|we have got|we have|we've|we got|there are|there's|there is) {_NUMBER} {_UNIT}{_ITEM}"
                    rf"(?P<where>{_WHERE})(?P<left> left)?")
_ADD = re.compile(rf"{_WHO}(?:bought|got|picked up|added|put|stocked up on|stocked) {_NUMBER} {_UNIT}(?:more )?{_ITEM}"
                  rf"(?P<where>{_WHERE})")
_MINIMUM = (
    re.compile(rf"(?:always )?(?:keep|have) (?:at least |a minimum of )?{_NUMBER} {_UNIT}{_ITEM}(?: in stock| in the {_PANTRY})?"),
    re.compile(rf"(?:set )?(?:the )?minimum (?:for|of) {_ITEM} (?:to|is|at|should be) {_NUMBER}(?: {_UNIT})?"),
    re.compile(rf"(?:we )?never (?:want to )?(?:have |go )?(?:less|fewer) than {_NUMBER} {_UNIT}{_ITEM}"),
)
_COUNT = re.compile(rf"how (?:many|much) {_UNIT}{_ITEM} (?:do we have|have we got|are left|is left|are there|is there|do we have left)(?: left)?")
_HAVE = re.compile(rf"(?:do we have|have we got|have we|is there|are there|any) (?:any )?{_UNIT}{_ITEM}(?: left| in the {_PANTRY})?")
_LOW_LIST = re.compile(r"what(?:'s| is| are we) (?:running )?low(?: on)?(?: in the (?:pantry|cupboard))?|"
                       r"what (?:do we need to restock|needs restocking)|what's in the (?:pantry|cupboard)|"
                       r"(?:pantry|stock) (?:report|check)|check the (?:pantry|stock)")
_FORGET = re.compile(rf"(?:stop (?:counting|tracking|keeping track of)|forget) {_ITEM}(?: (?:in|from) the {_PANTRY})?")
# Phrases that look like stock but aren't food or household supplies.
_NOT_ITEMS = frozenset({"time", "guests", "people", "visitors", "minutes", "hours", "days", "weeks", "patience",
                        "lights", "light", "music", "it", "that", "this", "them", "ideas", "options", "space",
                        "battery", "charge", "money", "data", "luck", "the shopping list", "shopping list", "list"})

LINES = {
    "stock": ("Counted. Someone in this house has to.",
              "Noted. I'm a butler, not a bloody stocktaker. But fine."),
    "used": ("Another one bites the dust.",
             "Spag bol again, is it?"),
    "low": ("Restock time. The cupboard's starting to look like a student flat.",
            "Running low, my bru. Unlike the appetites around here."),
    "out": ("Gone. Shocking. Nobody could have seen that coming.",
            "Out. Eish."),
    "minimum": ("Fine. I'll nag when it gets low.",
                "Minimum set. I'll be the responsible adult, again."),
    "guest": ("Nice try. Only the household changes the stock.",),
}
TOPICS = {
    "stock": "after counting what's in the pantry for the household",
    "used": "someone has just used up one of something from the pantry",
    "low": "the pantry is running low on something, so it's going on the shopping list",
    "out": "the household has run out of something, so it's going on the shopping list",
    "minimum": "agreeing to warn the household when a pantry item runs low",
    "guest": "refusing to let a guest change the household's pantry counts",
}


def _connect(path=None):
    path = Path(PATH if path is None else path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    db.execute("CREATE TABLE IF NOT EXISTS stock (key TEXT PRIMARY KEY, item TEXT NOT NULL, unit TEXT, "
               "count INTEGER NOT NULL, minimum INTEGER NOT NULL DEFAULT 0, updated_at REAL NOT NULL)")
    return db


def _clean(text):
    return " ".join(text.casefold().replace("’", "'").split()).strip(" ?.!,")


def key_for(item):
    words = [word for word in re.sub(r"[^a-z0-9 ]", " ", item.casefold()).split()
             if word not in {"the", "my", "our", "a", "an", "some", "any", "more"}]
    # Singular-ish, so "tomato" finds "tomatoes" and "tin of beans" finds "beans".
    def single(word):
        if len(word) > 4 and word.endswith("oes"):
            return word[:-2]
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            return word[:-1]
        return word
    return " ".join(single(word) for word in words)


def _number(text):
    if text is None:
        return None
    return int(text) if text.isdigit() else _WORDS.get(text)


def _unit(text):
    if not text:
        return None
    singular = {"loaves": "loaf", "boxes": "box", "bunches": "bunch", "kilos": "kilo", "kg": "kilo"}
    return singular.get(text, text[:-1] if text.endswith("s") and text != "dozen" else text)


def _item_ok(item):
    item = (item or "").strip()
    return (bool(item) and item not in _NOT_ITEMS and key_for(item) not in _NOT_ITEMS
            and len(item.split()) <= 5 and bool(key_for(item)))


def match(text):
    """(kind, payload) or None. kind: used, out, low, stock, add, minimum, count, have, list, forget."""
    if not isinstance(text, str):
        return None
    text = re.sub(r"^(?:(?:hey|ok|okay|howzit) )?declan,? ", "", _clean(text))
    text = re.sub(r",? (?:declan|please|my bru)$", "", text)
    if _LOW_LIST.fullmatch(text):
        return ("list", None)
    if (found := _FORGET.fullmatch(text)) and _item_ok(found["item"]) and (
            "pantry" in text or "cupboard" in text or text.startswith("stop")):
        return ("forget", found["item"].strip())
    for pattern in _MINIMUM:
        if (found := pattern.fullmatch(text)) and _item_ok(found["item"]):
            return ("minimum", (found["item"].strip(), _number(found["count"]), _unit(found["unit"])))
    if (found := _COUNT.fullmatch(text)) and _item_ok(found["item"]):
        return ("count", found["item"].strip())
    if (found := _USED.fullmatch(text)) and _item_ok(found["item"]):
        count = _number(found["count"])
        everything = bool(found["last"] or found["up"] or found["verb"] == "finished") and count is None
        return ("used", (found["item"].strip(), None if everything else count or 1, _unit(found["unit"])))
    if found := _OUT.fullmatch(text):
        item = next(value for value in found.groups() if value)
        if _item_ok(item):
            return ("out", item.strip())
    if (found := _LOW.fullmatch(text)) and _item_ok(found["item"]):
        return ("low", found["item"].strip())
    for kind, pattern in (("stock", _STOCK), ("add", _ADD)):
        found = pattern.fullmatch(text)
        # "We've got 3 guests" isn't stock: it needs a unit, a pantry place or "left".
        if (found and _item_ok(found["item"]) and _number(found["count"]) is not None
                and (found["unit"] or found["where"] or (kind == "stock" and found.groupdict().get("left")))):
            return (kind, (found["item"].strip(), _number(found["count"]), _unit(found["unit"])))
    if (found := _HAVE.fullmatch(text)) and _item_ok(found["item"]):
        return ("have", found["item"].strip())
    return None


def find(item, *, path=None):
    """The best stored match: exact, then word containment, then a close spelling."""
    wanted = key_for(item)
    if not wanted:
        return None
    with closing(_connect(path)) as db:
        rows = db.execute("SELECT key, item, unit, count, minimum FROM stock").fetchall()
    exact = [row for row in rows if row[0] == wanted]
    if exact:
        return exact[0]
    words = set(wanted.split())
    containing = [row for row in rows if words <= set(row[0].split()) or set(row[0].split()) <= words]
    if len(containing) == 1:
        return containing[0]
    close = difflib.get_close_matches(wanted, [row[0] for row in rows], n=1, cutoff=0.82)
    return next((row for row in rows if row[0] == close[0]), None) if close else None


def _store(key, item, unit, count, minimum, *, now, path):
    with closing(_connect(path)) as db, db:
        exists = db.execute("SELECT 1 FROM stock WHERE key = ?", (key,)).fetchone()
        if not exists and db.execute("SELECT COUNT(*) FROM stock").fetchone()[0] >= MAX_ITEMS:
            raise ValueError("I'm counting too many things already. Tell me to stop counting a few first.")
        db.execute("INSERT INTO stock VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET item = excluded.item, "
                   "unit = excluded.unit, count = excluded.count, minimum = excluded.minimum, "
                   "updated_at = excluded.updated_at",
                   (key, item, unit, max(0, min(MAX_COUNT, count)), max(0, min(MAX_COUNT, minimum)), now))


def forget(item, *, path=None):
    row = find(item, path=path)
    if row is None:
        return None
    with closing(_connect(path)) as db, db:
        db.execute("DELETE FROM stock WHERE key = ?", (row[0],))
    return row[1]


def listing(*, path=None):
    with closing(_connect(path)) as db:
        rows = db.execute("SELECT item, unit, count, minimum, updated_at FROM stock ORDER BY item").fetchall()
    return [{"item": item, "unit": unit or "", "count": count, "minimum": minimum, "updated_at": updated_at}
            for item, unit, count, minimum, updated_at in rows]


def _amount(count, unit, item):
    if not unit:
        return f"{count} {item}"
    units = {"loaf": "loaves", "box": "boxes", "bunch": "bunches", "dozen": "dozen"}
    plural = unit if count == 1 else units.get(unit, unit + "s")
    return f"{count} {plural} of {item}"


def _line(kind):
    from declan.turn import line_freshness
    return line_freshness.pick("pantry:" + kind, LINES[kind], topic=TOPICS[kind], polite=False)


def _title(item):
    return item[:1].upper() + item[1:]


def answer(request, *, guest=False, add_to_list=None, now=None, path=None):
    """Spoken reply, or None to let the rest of Declan answer.

    add_to_list(item) puts an item on the shopping list and returns "added",
    "already" or "unavailable". It's only called when stock runs out or low.
    """
    kind, payload = request
    now = time() if now is None else now

    def shopping(item):
        state = add_to_list(item) if add_to_list is not None else "unavailable"
        return {"added": "It's on the shopping list.", "already": "It's already on the shopping list."}.get(
            state, "I couldn't get it onto the shopping list, so write it down the old-fashioned way.")

    if kind == "list":
        rows = listing(path=path)
        if not rows:
            return "I'm not counting anything yet. Tell me what's in the cupboard, like 'we've got 6 tins of tomatoes'."
        low = [row for row in rows if row["count"] == 0 or row["count"] < row["minimum"]]
        if not low:
            return f"Nothing's running low. I'm counting {len(rows)} things, and for once we're stocked."
        names = [f"{row['item']} ({row['count']})" for row in low[:8]]
        more = f" and {len(low) - 8} more" if len(low) > 8 else ""
        return "Running low: " + ", ".join(names) + more + "."
    if kind in {"count", "have"}:
        row = find(payload, path=path)
        if row is None:
            return f"I'm not counting {payload}. Tell me how many we've got and I will." if kind == "count" else None
        _, item, unit, count, _ = row
        if count == 0:
            return f"No {item} left, my bru."
        return f"{_amount(count, unit, item)}{' left' if kind == 'count' else ', yes'}."
    if kind in {"out", "low"}:
        row = find(payload, path=path)
        item = row[1] if row else payload
        if row is not None and kind == "out":
            _store(row[0], row[1], row[2], 0, row[4], now=now, path=path)
        return f"{_line(kind)} {shopping(_title(item))}"
    if guest and kind in {"stock", "add", "minimum", "forget"}:
        return _line("guest")
    if kind == "forget":
        removed = forget(payload, path=path)
        return f"I've stopped counting {removed}." if removed else f"I wasn't counting {payload} anyway."
    item, number, unit = payload
    row = find(item, path=path)
    key, name = (row[0], row[1]) if row else (key_for(item), item)
    unit = unit or (row[2] if row else None)
    if kind == "minimum":
        count = row[3] if row else 0
        _store(key, name, unit, count, number, now=now, path=path)
        tail = "" if row else f" I don't know how many we've got, though. Tell me, like 'we've got 6 {unit + 's of ' if unit else ''}{name}'."
        return f"{_line('minimum')} At least {_amount(number, unit, name)}.{tail}"
    if kind in {"stock", "add"}:
        count = number + (row[3] if row and kind == "add" else 0)
        minimum = row[4] if row else 0
        _store(key, name, unit, count, minimum, now=now, path=path)
        return f"{_line('stock')} {_title(_amount(count, unit, name))}."
    # used
    if row is None:
        return (f"I wasn't counting {item}. Tell me how many we've got, like "
                f"'we've got 6 {unit + 's of ' if unit else ''}{item}', and I'll keep track.")
    _, name, unit, count, minimum = row
    left = 0 if number is None else max(0, count - number)
    _store(key, name, unit, left, minimum, now=now, path=path)
    if left == 0:
        return f"{_line('out')} That was the last of the {name}. {shopping(_title(name))}"
    if left < minimum:
        return f"{_line('low')} {_title(_amount(left, unit, name))} left. {shopping(_title(name))}"
    return f"{_line('used')} {_title(_amount(left, unit, name))} left."
