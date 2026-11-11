"""Household timers with durable deadlines and satellite-specific alarms."""

import json
import math
import os
import re
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from time import time
from threading import Lock
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request


DATABASE = Path(__file__).resolve().parent / ".data" / "timers.sqlite3"
ALARM_INTERVAL = 30
MAX_SECONDS = 24 * 60 * 60
SMALL_NUMBERS = dict(zip(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split(),
    range(20),
))
TENS = dict(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10)))
UNIT = re.compile(r"\s*(.+?)\s*(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b")
SATELLITE_ID = re.compile(r"assist_satellite\.[a-z0-9_]+")
TARGET = r"(?P<target>.*?\btimers?)(?: in (?:the )?(?P<room>.+))?"
_SCHEMA_LOCK = Lock()
_initialized = set()


def duration_seconds(text):
    total = 0
    units = set()
    text = re.sub(r"(?<=\w)-(?=(?:hour|minute|second)s?\b)", " ", text.strip())
    while text:
        match = UNIT.match(text)
        if not match:
            return None
        number, unit = match.groups()
        number = number.strip().replace("-", " ")
        words = number.split()
        if re.fullmatch(r"[0-9]{1,5}", number):
            amount = int(number)
        elif number in SMALL_NUMBERS or number in TENS:
            amount = (SMALL_NUMBERS | TENS)[number]
        elif len(words) == 2 and words[0] in TENS and 1 <= SMALL_NUMBERS.get(words[1], 0) <= 9:
            amount = TENS[words[0]] + SMALL_NUMBERS[words[1]]
        else:
            return None
        factor = {"h": 3600, "m": 60, "s": 1}[unit[0]]
        if factor in units:
            return None
        units.add(factor)
        total += amount * factor
        text = re.sub(r"^and\s+", "", text[match.end():].strip())
    return total if 0 < total <= MAX_SECONDS else None


def format_duration(seconds, *, hyphen=False):
    parts = []
    for name, factor in (("hour", 3600), ("minute", 60), ("second", 1)):
        value, seconds = divmod(seconds, factor)
        if value:
            parts.append(f"{value}-{name}" if hyphen else f"{value} {name}{'s' if value != 1 else ''}")
    return " ".join(parts) or "0 seconds"


def initialize():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with _SCHEMA_LOCK:
        identity = (DATABASE.resolve(), DATABASE.stat().st_ino) if DATABASE.exists() else None
        if identity in _initialized:
            return
        with closing(sqlite3.connect(DATABASE, timeout=2)) as connection, connection:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute("""CREATE TABLE IF NOT EXISTS timers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, satellite TEXT NOT NULL,
            room TEXT NOT NULL, deadline REAL NOT NULL, next_alarm REAL NOT NULL,
            last_alarm_ok INTEGER, UNIQUE(name COLLATE NOCASE, room COLLATE NOCASE)
            )""")
        _initialized.add((DATABASE.resolve(), DATABASE.stat().st_ino))


@contextmanager
def database():
    initialize()
    with closing(sqlite3.connect(DATABASE, timeout=2)) as connection, connection:
        connection.row_factory = sqlite3.Row
        yield connection


def ha_json(opener, path, *, data=None, timeout=2):
    url = os.environ.get("DECLAN_HA_URL", "").strip().rstrip("/")
    token = os.environ.get("DECLAN_HA_TOKEN", "").strip()
    parsed = urlsplit(url)
    if (not token or parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("Home Assistant is not configured")
    request = Request(url + path, data=json.dumps(data).encode() if data is not None else None,
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with opener.open(request, timeout=timeout) as response:
            return json.loads(response.read(65536))
    except HTTPError as error:
        error.close()
        raise ValueError("Home Assistant rejected the timer request") from None


def resolve_output(opener, satellite, device, *, browser=False, room=None):
    if room is not None:
        satellite = None
        template = (
            "{% set matches = namespace(ids=[]) %}"
            "{% for id in areas() %}"
            "{% if area_name(id) | lower == " + json.dumps(room, ensure_ascii=False) + " %}"
            "{% set matches.ids = matches.ids + [id] %}"
            "{% endif %}{% endfor %}"
        )
        candidates = "(area_entities(matches.ids[0]) if matches.ids | count == 1 else [])"
    elif browser:
        satellite = os.environ.get("DECLAN_BROWSER_TIMER_SATELLITE", "").strip()
        device = None
    if room is None:
        if satellite and not SATELLITE_ID.fullmatch(satellite):
            return None
        if not satellite and not device:
            return None
        candidates = json.dumps([satellite]) if satellite else "device_entities(" + json.dumps(device) + ")"
        template = ""
    template += (
        "{% set outputs = " + candidates + " | select('match', '^assist_satellite[.]') | list %}"
        "{% if outputs | count == 1 %}{% set output = outputs[0] %}"
        "{{ [output, area_name(output) or state_attr(output, 'friendly_name') or output, states(output)] | to_json }}"
        "{% else %}[]{% endif %}"
    )
    result = ha_json(opener, "/api/template", data={"template": template})
    if (isinstance(result, list) and len(result) == 3 and all(isinstance(value, str) for value in result)
            and SATELLITE_ID.fullmatch(result[0]) and (not satellite or satellite == result[0])
            and result[2] not in ("unknown", "unavailable")):
        return result[0], result[1]
    return None


def timer_name(text):
    name = re.sub(r"^(?:(?:the|my|a|an)\s+)+", "", text.strip())
    name = re.sub(r"(?:^|\s+)timers?$", "", name).strip()
    duration = duration_seconds(name) if name else None
    return format_duration(duration, hyphen=True) + " timer" if duration else name


def timer_label(name):
    return name if name.endswith(" timer") else name + " timer"


def describe(timer, now):
    label = f"The {timer_label(timer['name'])} in {timer['room']}"
    if timer["deadline"] > now:
        return f"{label} has {format_duration(math.ceil(timer['deadline'] - now))} left"
    if timer["last_alarm_ok"] == 0:
        return f"{label}, expired, but I couldn't confirm its alarm was delivered"
    if timer["last_alarm_ok"] is None:
        return f"{label} has expired. Its alarm hasn't been confirmed yet"
    return f"{label}, expired and awaiting acknowledgement"


def handle(phrase, opener, *, satellite=None, device=None, browser=False):
    creation_text = phrase
    destination = None
    if phrase.startswith("set "):
        creation_text, separator, room = phrase.rpartition(" in ")
        if separator:
            destination = room.removeprefix("the ").strip()
        else:
            creation_text = phrase
    creation = re.fullmatch(r"set (?:a |an )?(?:(.+?) )?timer for (.+)", creation_text)
    duration_first = re.fullmatch(r"set (?:a |an )?(.+?) timer", creation_text) if not creation else None
    query = re.fullmatch(r"how much time is (?:left )?on " + TARGET, phrase)
    removal = re.fullmatch(r"(cancel|stop|acknowledge) " + TARGET, phrase)
    adjustment = re.fullmatch(r"(increase|decrease) (?:the time on )?" + TARGET + r" by (?P<amount>.+)", phrase)
    list_all = phrase in {"what timers are running", "list timers", "list my timers"}
    if not (creation or duration_first or query or removal or adjustment or list_all):
        return None
    try:
        if creation or duration_first:
            prefix, duration_text = creation.groups() if creation else (None, duration_first[1])
            duration_text, separator, suffix = duration_text.partition(" for ")
            duration = duration_seconds(duration_text)
            if duration is None:
                return "Give me a duration between one second and 24 hours.", "unresolved"
            name = timer_name(prefix or suffix) if prefix or separator else format_duration(duration, hyphen=True) + " timer"
            if not name or len(name) > 60 or (prefix and separator):
                return "Please give the timer one name of up to 60 characters.", "unresolved"
            name = name[0].upper() + name[1:]
            if destination == "":
                return "Which room should this timer ring in?", "unresolved"
            output = resolve_output(opener, satellite, device, browser=browser, room=destination)
            if output is None:
                if destination is not None:
                    return f"I couldn't identify one available Assist satellite in {destination}. The timer wasn't set.", "unavailable"
                return "I couldn't verify an alarm output. Set the timer from an available Assist satellite or configure a browser timer output.", "unavailable"
            deadline = time() + duration
            with database() as db:
                db.execute("BEGIN IMMEDIATE")
                if db.execute("SELECT count(*) FROM timers").fetchone()[0] >= 32:
                    return "There are already 32 timers. Cancel or acknowledge one first.", "unavailable"
                try:
                    db.execute("INSERT INTO timers(name,satellite,room,deadline,next_alarm) VALUES (?,?,?,?,?)",
                               (name, *output, deadline, deadline))
                except sqlite3.IntegrityError:
                    return f"There's already a timer named {name} in {output[1]}. Use a different name.", "unresolved"
            return f"Set {name} for {format_duration(duration)}. Alarm output: {output[1]}.", "timer_set"

        amount = duration_seconds(adjustment["amount"]) if adjustment else None
        if adjustment and amount is None:
            return "Give me a duration between one second and 24 hours.", "unresolved"
        match = query or removal or adjustment
        name = timer_name(match["target"]) if match else ""
        room = match["room"] if match else None
        now = time()
        with database() as db:
            if removal or adjustment:
                db.execute("BEGIN IMMEDIATE")
            timers = db.execute("SELECT * FROM timers ORDER BY deadline, id").fetchall()
            matches = [timer for timer in timers
                       if (not name or timer["name"].casefold() == name.casefold())
                       and (not room or timer["room"].casefold() == room.casefold())]
            if adjustment and name and not room and not matches:
                matches = [timer for timer in timers if timer["room"].casefold() == name.casefold()]
            if not matches:
                return "I couldn't find a matching timer." if name or room else "There are no timers.", "no_timer"
            if len(matches) > 1 and (name or removal or adjustment):
                options = ". ".join(describe(timer, now) for timer in matches)
                return f"Which timer do you mean? {options}.", "unresolved"
            if not (removal or adjustment):
                return ". ".join(describe(timer, now) for timer in matches) + ".", "timer_status"
            timer = matches[0]
            expired = timer["deadline"] <= now
            named_timer = timer_label(timer["name"])
            if adjustment:
                if expired:
                    return f"The {named_timer} in {timer['room']} has already expired.", "unresolved"
                increase = adjustment[1] == "increase"
                deadline = timer["deadline"] + (amount if increase else -amount)
                if deadline - now > MAX_SECONDS:
                    return "A timer can't have more than 24 hours left.", "unresolved"
                deadline = max(now, deadline)
                db.execute("UPDATE timers SET deadline = ?, next_alarm = ?, last_alarm_ok = NULL WHERE id = ?",
                           (deadline, deadline, timer["id"]))
                remaining = math.ceil(deadline - now)
                label = f"The {named_timer} in {timer['room']}"
                return (f"{label} now has {format_duration(remaining)} left." if remaining
                        else f"{label} is due now."), "timer_adjusted"
            if removal[1] == "cancel" and expired:
                return f"{timer['name']} has already expired. Say stop the {named_timer} to silence its alarm.", "unresolved"
            if removal[1] != "cancel" and not expired:
                return f"{timer['name']} is still running. Say cancel the {named_timer} to cancel it.", "unresolved"
            db.execute("DELETE FROM timers WHERE id = ?", (timer["id"],))
            verb = "Cancelled" if not expired else "Stopped the alarm for"
            return f"{verb} {timer['name']}.", "timer_cancelled" if not expired else "timer_stopped"
    except (OSError, ValueError, sqlite3.Error):
        return "I couldn't complete that timer request.", "unavailable"


def stop_due(satellite):
    """Acknowledge expired alarms on one satellite without cancelling running timers."""
    with database() as db:
        db.execute("DELETE FROM timers WHERE satellite = ? AND deadline <= ?", (satellite, time()))


def ring_due(opener):
    """Claim one due alarm and send a short chime without stopping other audio."""
    now = time()
    with database() as db:
        timer = db.execute("SELECT * FROM timers WHERE next_alarm <= ? ORDER BY next_alarm LIMIT 1", (now,)).fetchone()
        if timer is None:
            return
        # Claim only if another poller/cancellation/adjustment has not changed it.
        changed = db.execute("UPDATE timers SET next_alarm = ? WHERE id = ? AND next_alarm = ? AND deadline = ?",
                             (now + ALARM_INTERVAL, timer['id'], timer['next_alarm'], timer['deadline']))
        if changed.rowcount != 1:
            return
    with database() as db:
        if db.execute("SELECT 1 FROM timers WHERE id = ? AND deadline = ?", (timer["id"], timer["deadline"])).fetchone() is None:
            return
    media = os.environ.get("DECLAN_TIMER_ALARM_MEDIA_ID", "").strip()
    target = {"entity_id": timer["satellite"]}
    try:
        if media.startswith("media-source://"):
            try:
                ha_json(opener, "/api/services/assist_satellite/announce",
                        data={**target, "media_id": media, "preannounce": False}, timeout=7)
            except ValueError:
                media = ""
        if not media.startswith("media-source://"):
            ha_json(opener, "/api/services/assist_satellite/announce",
                    data={**target, "message": f"Your {timer_label(timer['name'])} is up.", "preannounce": True},
                    timeout=7)
        delivered = True
    except (OSError, ValueError):
        delivered = False
    with database() as db:
        db.execute("UPDATE timers SET last_alarm_ok = ? WHERE id = ? AND deadline = ?",
                   (delivered, timer["id"], timer["deadline"]))
