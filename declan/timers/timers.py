"""Household timers with durable deadlines and satellite-specific alarms."""

import json
import math
import os
import re
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from time import time
from declan.timers import timer_schema_state
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request

from declan.core.execution_results import ExecutionResult, Outcome
from declan.ha import ha_replies


DATABASE = Path(__file__).resolve().parents[2] / ".data" / "timers.sqlite3"
ALARM_INTERVAL = 30
# A ringing alarm gives up after this long, so it can never repeat forever.
ALARM_GIVE_UP_SECONDS = 10 * 60
# While an alarm is ringing, these silence it (on top of "stop the timer").
ALARM_STOP_PHRASES = frozenset({
    "stop", "stop it", "stop that", "ok stop", "okay stop", "stop the alarm", "stop alarm",
    "cancel the alarm", "cancel alarm", "turn off the alarm", "turn the alarm off", "alarm off",
    "silence", "silence the alarm", "be quiet", "quiet", "shut up", "dismiss", "dismiss the alarm",
    "thanks", "thank you", "ok", "okay", "got it",
})
MAX_SECONDS = 24 * 60 * 60
SMALL_NUMBERS = dict(zip(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split(),
    range(20),
))
TENS = dict(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10)))
UNIT = re.compile(r"\s*(.+?)\s*(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b")
SATELLITE_ID = re.compile(r"assist_satellite\.[a-z0-9_]+")
TARGET = r"(?P<target>.*?\btimers?)(?: in (?:the )?(?P<room>.+))?"
SCHEMA_STATE = timer_schema_state.TimerSchemaState()


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
    def create_schema():
        with closing(sqlite3.connect(DATABASE, timeout=2)) as connection, connection:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute("""CREATE TABLE IF NOT EXISTS timers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, satellite TEXT NOT NULL,
            room TEXT NOT NULL, deadline REAL NOT NULL, next_alarm REAL NOT NULL,
            last_alarm_ok INTEGER, UNIQUE(name COLLATE NOCASE, room COLLATE NOCASE)
            )""")

    SCHEMA_STATE.ensure(DATABASE, create_schema)

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
            return ha_replies.decode(response, path, 65536)
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
    from declan.timers import reminders
    if reminders.is_reminder(name):
        return reminders.label(name)
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


def ringing():
    """True while at least one timer has expired and its alarm is still sounding."""
    try:
        with database() as db:
            return db.execute("SELECT 1 FROM timers WHERE deadline <= ? LIMIT 1", (time(),)).fetchone() is not None
    except (OSError, sqlite3.Error):
        return False


def matches(phrase):
    """Recognise timer requests; plain "stop" only while an alarm is ringing."""
    from declan.timers import sunrise
    if phrase in ALARM_STOP_PHRASES:
        return ringing() or sunrise.active()  # FUT-45: "stop" ends a running sunrise too
    sunrise_request = sunrise.parse(phrase)
    if sunrise_request is not None:
        return sunrise_request[0] != "snooze" or sunrise.active()
    from declan.timers import reminders
    if reminders.parse(phrase) is not None:  # FUT-26
        return True
    creation_text = phrase.rpartition(" in ")[0] if phrase.startswith("set ") and " in " in phrase else phrase
    creation = re.fullmatch(r"set (?:a |an )?(?:(.+?) )?timer for (.+)", creation_text)
    duration_first = re.fullmatch(r"set (?:a |an )?(.+?) timer", creation_text) if not creation else None
    return bool(creation or duration_first
                or re.fullmatch(r"how much time is (?:left )?on " + TARGET, phrase)
                or re.fullmatch(r"(cancel|stop|acknowledge) " + TARGET, phrase)
                or re.fullmatch(r"(increase|decrease) (?:the time on )?" + TARGET + r" by (?P<amount>.+)", phrase)
                or phrase in {"what timers are running", "list timers", "list my timers"})


def handle_result(phrase, opener, *, satellite=None, device=None, browser=False):
    """Typed timer provider outcome; None means the phrase did not match."""
    from declan.timers import sunrise
    if phrase in ALARM_STOP_PHRASES:
        ended = sunrise.stop(satellite, opener=opener) if sunrise.active() else None
        if not ringing():
            return ended or _silence(satellite)
        silenced = _silence(satellite)
        if ended is None:
            return silenced
        return ExecutionResult(f"{ended.reply} {silenced.reply}", Outcome.TIMER_STOPPED)
    sunrise_request = sunrise.parse(phrase)
    if sunrise_request is not None:  # FUT-45
        return sunrise.command(sunrise_request, opener, satellite=satellite, device=device, browser=browser)
    from declan.timers import reminders
    reminder = reminders.parse(phrase)
    if reminder is not None:
        return _reminder_result(reminder, opener, satellite, device, browser)
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
            if creation is not None:
                prefix, duration_text = creation.groups()
            else:
                if duration_first is None:
                    return None
                prefix, duration_text = None, duration_first[1]
            duration_text, separator, suffix = duration_text.partition(" for ")
            duration = duration_seconds(duration_text)
            if duration is None:
                return ExecutionResult("Give me a duration between one second and 24 hours.", Outcome.UNRESOLVED)
            name = timer_name(prefix or suffix) if prefix or separator else format_duration(duration, hyphen=True) + " timer"
            if not name or len(name) > 60 or (prefix and separator):
                return ExecutionResult("Please give the timer one name of up to 60 characters.", Outcome.UNRESOLVED)
            name = name[0].upper() + name[1:]
            if destination == "":
                return ExecutionResult("Which room should this timer ring in?", Outcome.UNRESOLVED)
            output = resolve_output(opener, satellite, device, browser=browser, room=destination)
            if output is None:
                if destination is not None:
                    return ExecutionResult(f"I couldn't identify one available Assist satellite in {destination}. The timer wasn't set.", Outcome.UNAVAILABLE)
                return ExecutionResult("I couldn't verify an alarm output. Set the timer from an available Assist satellite or configure a browser timer output.", Outcome.UNAVAILABLE)
            deadline = time() + duration
            with database() as db:
                db.execute("BEGIN IMMEDIATE")
                if db.execute("SELECT count(*) FROM timers").fetchone()[0] >= 32:
                    return ExecutionResult("There are already 32 timers. Cancel or acknowledge one first.", Outcome.UNAVAILABLE)
                try:
                    db.execute("INSERT INTO timers(name,satellite,room,deadline,next_alarm) VALUES (?,?,?,?,?)",
                               (name, *output, deadline, deadline))
                except sqlite3.IntegrityError:
                    return ExecutionResult(f"There's already a timer named {name} in {output[1]}. Use a different name.", Outcome.UNRESOLVED)
            return ExecutionResult(f"Set {name} for {format_duration(duration)}. Alarm output: {output[1]}.", Outcome.TIMER_SET)

        amount = duration_seconds(adjustment["amount"]) if adjustment else None
        if adjustment and amount is None:
            return ExecutionResult("Give me a duration between one second and 24 hours.", Outcome.UNRESOLVED)
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
                return ExecutionResult("I couldn't find a matching timer." if name or room else "There are no timers.", Outcome.NO_TIMER)
            if len(matches) > 1 and (name or removal or adjustment):
                options = ". ".join(describe(timer, now) for timer in matches)
                return ExecutionResult(f"Which timer do you mean? {options}.", Outcome.UNRESOLVED)
            if not (removal or adjustment):
                return ExecutionResult(". ".join(describe(timer, now) for timer in matches) + ".", Outcome.TIMER_STATUS)
            timer = matches[0]
            expired = timer["deadline"] <= now
            named_timer = timer_label(timer["name"])
            if adjustment:
                if amount is None:
                    return ExecutionResult("Give me a valid timer adjustment.", Outcome.UNRESOLVED)
                if expired:
                    return ExecutionResult(f"The {named_timer} in {timer['room']} has already expired.", Outcome.UNRESOLVED)
                increase = adjustment[1] == "increase"
                deadline = timer["deadline"] + (amount if increase else -amount)
                if deadline - now > MAX_SECONDS:
                    return ExecutionResult("A timer can't have more than 24 hours left.", Outcome.UNRESOLVED)
                deadline = max(now, deadline)
                db.execute("UPDATE timers SET deadline = ?, next_alarm = ?, last_alarm_ok = NULL WHERE id = ?",
                           (deadline, deadline, timer["id"]))
                remaining = math.ceil(deadline - now)
                label = f"The {named_timer} in {timer['room']}"
                return ExecutionResult(f"{label} now has {format_duration(remaining)} left." if remaining
                        else f"{label} is due now.", Outcome.TIMER_ADJUSTED)
            if removal is None:
                return None
            # "Cancel" and "stop" mean the same to people: a running timer is
            # cancelled and a ringing one is silenced, whichever word was used.
            db.execute("DELETE FROM timers WHERE id = ?", (timer["id"],))
            verb = "Cancelled" if not expired else "Stopped the alarm for"
            return ExecutionResult(f"{verb} {timer['name']}.", Outcome.TIMER_CANCELLED if not expired else Outcome.TIMER_STOPPED)
    except (OSError, ValueError, sqlite3.Error):
        return ExecutionResult("I couldn't complete that timer request.", Outcome.UNAVAILABLE)


def _when(deadline, now):
    from datetime import datetime
    moment, today = datetime.fromtimestamp(deadline).astimezone(), datetime.fromtimestamp(now).astimezone()
    if deadline - now < 3600:
        return "in " + format_duration(max(60, round((deadline - now) / 60) * 60))
    day = "" if moment.date() == today.date() else ("tomorrow " if (moment.date() - today.date()).days == 1
                                                    else f"on {moment:%A} ")
    return f"{day}at {moment:%H:%M}"


def _reminder_result(request, opener, satellite, device, browser):
    """FUT-26: set, list or cancel reminders, stored as timers that speak their message."""
    from declan.timers import reminders
    now = time()
    try:
        if request[0] == "set":
            _, name, deadline = request
            if deadline is None:
                return ExecutionResult("When should I remind you? Say \"at six\" or \"in 20 minutes\".", Outcome.UNRESOLVED)
            if deadline - now > reminders.MAX_SECONDS:
                return ExecutionResult("I can only remind you up to a week ahead.", Outcome.UNRESOLVED)
            output = resolve_output(opener, satellite, device, browser=browser)
            if output is None:
                return ExecutionResult("I couldn't tell which room to remind you in. Ask me from a satellite.", Outcome.UNAVAILABLE)
            with database() as db:
                db.execute("BEGIN IMMEDIATE")
                if db.execute("SELECT count(*) FROM timers").fetchone()[0] >= 32:
                    return ExecutionResult("There are already 32 timers and reminders. Cancel one first.", Outcome.UNAVAILABLE)
                db.execute("INSERT INTO timers(name,satellite,room,deadline,next_alarm) VALUES (?,?,?,?,?) "
                           "ON CONFLICT(name COLLATE NOCASE, room COLLATE NOCASE) DO UPDATE SET deadline = excluded.deadline, "
                           "next_alarm = excluded.next_alarm, satellite = excluded.satellite, last_alarm_ok = NULL",
                           (name, *output, deadline, deadline))
            return ExecutionResult(f"I'll remind you {_when(deadline, now)}: {name.removeprefix(reminders.PREFIX)}.",
                                   Outcome.TIMER_SET)
        with database() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = [row for row in db.execute("SELECT * FROM timers ORDER BY deadline, id").fetchall()
                    if reminders.is_reminder(row["name"])]
            if request[0] == "list":
                upcoming = [row for row in rows if row["deadline"] > now]
                if not upcoming:
                    return ExecutionResult("No reminders. You'll have to remember things yourself.", Outcome.TIMER_STATUS)
                parts = [f"{row['name'].removeprefix(reminders.PREFIX)} {_when(row['deadline'], now)}" for row in upcoming[:6]]
                count = f"{len(upcoming)} reminders" if len(upcoming) > 1 else "One reminder"
                return ExecutionResult(f"{count}: " + "; ".join(parts) + ".", Outcome.TIMER_STATUS)
            target = request[1]
            chosen = rows if target is None else [row for row in rows if target.casefold() in row["name"].casefold()]
            if not chosen:
                return ExecutionResult("I couldn't find that reminder." if target else "There are no reminders.", Outcome.NO_TIMER)
            if target is not None and len(chosen) > 1:
                options = "; ".join(row["name"].removeprefix(reminders.PREFIX) for row in chosen)
                return ExecutionResult(f"Which reminder? {options}.", Outcome.UNRESOLVED)
            db.executemany("DELETE FROM timers WHERE id = ?", [(row["id"],) for row in chosen])
        if target is None:
            return ExecutionResult(f"Cancelled {len(chosen)} reminder{'s' if len(chosen) != 1 else ''}.", Outcome.TIMER_CANCELLED)
        return ExecutionResult(f"Cancelled the {reminders.label(chosen[0]['name'])}.", Outcome.TIMER_CANCELLED)
    except (OSError, ValueError, sqlite3.Error):
        return ExecutionResult("I couldn't complete that reminder request.", Outcome.UNAVAILABLE)


def _silence(satellite):
    """Silence ringing alarms: this satellite's first, otherwise every ringing one."""
    try:
        with database() as db:
            db.execute("BEGIN IMMEDIATE")
            due = db.execute("SELECT * FROM timers WHERE deadline <= ? ORDER BY deadline, id", (time(),)).fetchall()
            if not due:
                return ExecutionResult("No alarm is ringing.", Outcome.NO_TIMER)
            mine = [timer for timer in due if satellite and timer["satellite"] == satellite]
            stopped = mine or due
            db.executemany("DELETE FROM timers WHERE id = ?", [(timer["id"],) for timer in stopped])
    except (OSError, sqlite3.Error):
        return ExecutionResult("I couldn't stop the alarm.", Outcome.UNAVAILABLE)
    names = " and the ".join(timer_label(timer["name"]) for timer in stopped)
    return ExecutionResult(f"Stopped the alarm for the {names}.", Outcome.TIMER_STOPPED)


def stop_due(satellite):
    """Acknowledge expired alarms on one satellite without cancelling running timers."""
    with database() as db:
        db.execute("DELETE FROM timers WHERE satellite = ? AND deadline <= ?", (satellite, time()))


def _notify_phones(opener, message):
    """Optional: DECLAN_REMINDER_NOTIFY lists notify services (notify.mobile_app_x, ...)."""
    for service in os.environ.get("DECLAN_REMINDER_NOTIFY", "").split(","):
        service = service.strip()
        if re.fullmatch(r"notify\.[a-z0-9_]{1,80}", service):
            try:
                ha_json(opener, "/api/services/notify/" + service.split(".", 1)[1],
                        data={"title": "Declan", "message": message}, timeout=5)
            except (OSError, ValueError):
                pass


def sunrise_due(opener, *, music_module=None, ha_connect=None, music_inventory=None):
    """FUT-45: move sunrise wake-ups along (lights, good morning, music fade)."""
    from declan.timers import sunrise
    music = (sunrise.MusicAssistant(music_module, ha_connect, music_inventory)
             if music_module is not None and ha_connect is not None and music_inventory is not None else None)
    sunrise.due(opener, music=music)


def ring_due(opener):
    """Claim one due alarm and send a short chime without stopping other audio."""
    now = time()
    with database() as db:
        timer = db.execute("SELECT * FROM timers WHERE next_alarm <= ? ORDER BY next_alarm LIMIT 1", (now,)).fetchone()
        if timer is None:
            return
        if timer["deadline"] <= now - ALARM_GIVE_UP_SECONDS:
            # Never ring forever: an alarm nobody stopped is dropped after ten minutes.
            db.execute("DELETE FROM timers WHERE id = ? AND deadline = ?", (timer["id"], timer["deadline"]))
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
        from declan.timers import reminders
        if media.startswith("media-source://") and not reminders.is_reminder(timer["name"]):
            try:
                ha_json(opener, "/api/services/assist_satellite/announce",
                        data={**target, "media_id": media, "preannounce": False}, timeout=7)
            except ValueError:
                media = ""
        if reminders.is_reminder(timer["name"]):
            # FUT-26: a reminder speaks its message instead of the alarm sound.
            message = reminders.spoken(timer["name"])
            ha_json(opener, "/api/services/assist_satellite/announce",
                    data={**target, "message": message, "preannounce": True}, timeout=7)
            if timer["last_alarm_ok"] is None:
                _notify_phones(opener, message)
        elif not media.startswith("media-source://"):
            ha_json(opener, "/api/services/assist_satellite/announce",
                    data={**target, "message": f"Your {timer_label(timer['name'])} is up.", "preannounce": True},
                    timeout=7)
        delivered = True
    except (OSError, ValueError):
        delivered = False
    with database() as db:
        db.execute("UPDATE timers SET last_alarm_ok = ? WHERE id = ? AND deadline = ?",
                   (delivered, timer["id"], timer["deadline"]))
