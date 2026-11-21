"""Sunrise wake-up (FUT-45, #834).

"Wake me at 6:30 with the sunrise": the dimmable bedroom lights brighten from
1% to full over the 15 minutes before 6:30 (warming from candle to daylight
where the bulb supports it), then Declan says good morning and quiet music
fades in on that room's speaker.

- "Wake me at 6:30 with the sunrise on weekdays" (or weekends, every day,
  tomorrow). "... and play Afrikaans" picks the music; "... without music".
- "When's my sunrise?", "cancel the sunrise", "skip tomorrow's sunrise".
- While it's running, "stop" turns off the lights it brightened and pauses
  the music; "snooze" pauses the music for 9 minutes and leaves the lights on.
- One sunrise per room, set from that room's satellite. Lights that can't dim,
  and lights already on when the ramp starts, are left alone.
- Music respects the household's single Spotify stream: if music is playing
  in another room, Declan leaves it alone and says so.
- Everything is stored (SQLite) and worked out from the clock, so a restart
  overnight carries on where it was. If Declan was down for more than 30
  minutes past the wake time, that morning is skipped instead of switching
  lights on late.

The car charge summary (Pod Point) waits for FUT-31.
"""
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from time import time

from declan.core.execution_results import ExecutionResult, Outcome

PATH = Path(__file__).resolve().parents[2] / ".data" / "sunrise.sqlite3"
RAMP_SECONDS = 15 * 60
STEP_SECONDS = 60
FADE_SECONDS = 5 * 60
AWAKE_SECONDS = 10 * 60  # "stop" works this long after the wake time
SNOOZE_SECONDS = 9 * 60
LATE_SECONDS = 30 * 60
VOLUME_START, VOLUME_END = 0.05, 0.25
KELVIN_START, KELVIN_END = 2200, 4000
ACTIVE = ("ramp", "awake", "snoozed")
DAYS = {"once": "tomorrow", "weekdays": "on weekdays", "weekends": "at weekends", "daily": "every day"}
_DEFAULT_MUSIC = "something good"

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                 "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
_HOUR = r"\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
_CLOCK = (rf"(?:(?P<hour>{_HOUR})(?:[:.](?P<minute>\d{{2}})| (?P<minute_words>o'clock|thirty|fifteen|forty five|forty-five))?"
          r"(?: ?(?P<ampm>am|pm|a\.m\.|p\.m\.|in the morning))?"
          rf"|half past (?P<half>{_HOUR})|quarter past (?P<quarter>{_HOUR}))")
_SUNRISE = r"(?:the |a )?sunrise(?: alarm| wake ?-?up)?"
_SET = (
    re.compile(rf"(?:please )?wake (?:me|us)(?: up)? (?:at )?{_CLOCK}(?P<rest>.*?) with {_SUNRISE}(?P<rest2>.*)"),
    re.compile(rf"(?:please )?wake (?:me|us)(?: up)? with {_SUNRISE} (?:at )?{_CLOCK}(?P<rest>.*)"),
    re.compile(rf"(?:set |start )?(?:a |the |my )?sunrise (?:alarm|wake ?-?up)(?: for| at)? {_CLOCK}(?P<rest>.*)"),
)
_DAY_WORDS = re.compile(r"(?:on |at )?(?P<days>weekdays|workdays|weekends|every day|everyday|every morning|daily|tomorrow)")
_ASK = re.compile(rf"(?:when(?:'s| is)|what time is) (?:my |the ){_SUNRISE}|is (?:my |the ){_SUNRISE} (?:set|on)")
_CANCEL = re.compile(rf"(?:cancel|delete|remove|turn off|switch off) (?:my |the ){_SUNRISE}")
_SKIP = re.compile(rf"(?:skip|no) (?:the |my )?(?:next |tomorrow's )?{_SUNRISE}(?: tomorrow)?")
SNOOZE_PHRASES = frozenset({"snooze", "snooze it", "snooze the alarm", "snooze the sunrise", "five more minutes",
                            "5 more minutes", "just five more minutes", "ten more minutes", "nine more minutes"})

LINES = {
    "wake": ("Morning, sunshine. The sun's up, and so are you, whether you like it or not.",
             "Rise and shine, my bru. I've been brightening this room for fifteen minutes, the least you can do is open your eyes.",
             "Howzit. It's morning. I don't make the rules. Well, I do, but not this one.",
             "Wakey wakey. The coffee won't make itself. Neither will I."),
    "snooze": ("Fine. Nine minutes. I'm counting.",
               "Snooze. Classic. I'll be back."),
    "stop": ("Sunrise off. Don't you dare go back to sleep.",
             "Fine, I'll stop. You're welcome for the gentle wake-up, by the way."),
}
TOPICS = {"wake": "waking someone up gently in the morning with a sunrise light and quiet music",
          "snooze": "someone hitting snooze on their morning wake-up",
          "stop": "someone switching off their morning wake-up"}


def _clean(text):
    text = " ".join(text.casefold().replace("’", "'").split()).strip(" ?.!")
    return re.sub(r"^(?:(?:hey|ok|okay|howzit) )?declan,? ", "", text)


def _hour(value):
    return int(value) if value.isdigit() else _NUMBER_WORDS[value]


def _clock(found):
    """(hour, minute) for a wake-up; a bare hour is in the morning."""
    if found["half"] or found["quarter"]:
        hour, minute = _hour(found["half"] or found["quarter"]), 30 if found["half"] else 15
    else:
        hour = _hour(found["hour"])
        words = found["minute_words"] or ""
        minute = int(found["minute"]) if found["minute"] else {"thirty": 30, "fifteen": 15}.get(
            words, 45 if "forty" in words else 0)
    if hour > 23 or minute > 59:
        return None
    if (found["ampm"] or "").startswith("p") and hour < 12:
        hour += 12
    elif (found["ampm"] or "").startswith(("a", "in the morning")) and hour == 12:
        hour = 0
    return hour, minute


def _days(word):
    if not word:
        return "once"
    if word == "tomorrow":
        return "once"
    if word in {"weekdays", "workdays"}:
        return "weekdays"
    if word == "weekends":
        return "weekends"
    return "daily"


def parse(phrase):
    """("set", hour, minute, days, music) | ("ask",) | ("cancel",) | ("skip",) | ("snooze",) or None.

    ``music`` is a title to play, "" for the default, or None for no music.
    """
    if not isinstance(phrase, str):
        return None
    text = _clean(phrase)
    if text in SNOOZE_PHRASES:
        return ("snooze",)
    if "sunrise" not in text:
        return None
    for kind, pattern in (("ask", _ASK), ("cancel", _CANCEL), ("skip", _SKIP)):
        if pattern.fullmatch(text):
            return (kind,)
    for pattern in _SET:
        found = pattern.fullmatch(text)
        if not found:
            continue
        clock = _clock(found)
        if clock is None:
            return None
        rest = " ".join(part for part in (found["rest"], found.groupdict().get("rest2") or "") if part).strip()
        days = None
        day = _DAY_WORDS.match(rest)
        if day:
            days, rest = day["days"], rest[day.end():].strip()
        music: str | None = ""
        if re.fullmatch(r"(?:and )?(?:without|with no|no) music", rest):
            music = None
        elif rest:
            played = re.fullmatch(r"(?:and |then )?(?:play |with )(?:some )?(?P<title>[a-z0-9' &-]{2,60}?)(?: music)?"
                                  r"(?: (?:on |at )?(?P<days>weekdays|workdays|weekends|every day|every morning|daily|tomorrow))?",
                                  rest)
            if not played:
                return None
            music, days = played["title"], days or played["days"]
        return ("set", *clock, _days(days), music)
    return None


def next_wake(hour, minute, days, now):
    """The next local time at hour:minute on an allowed day, strictly after ``now`` (an aware datetime)."""
    for offset in range(8):
        moment = (now + timedelta(days=offset)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        weekday = moment.weekday()
        if moment <= now or (days == "weekdays" and weekday >= 5) or (days == "weekends" and weekday < 5):
            continue
        return moment.timestamp()
    raise ValueError("No wake time found")


def _connect(path=None):
    path = Path(PATH if path is None else path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS wakes (room TEXT PRIMARY KEY, satellite TEXT NOT NULL, "
               "hour INTEGER NOT NULL, minute INTEGER NOT NULL, days TEXT NOT NULL, music TEXT, "
               "wake_at REAL NOT NULL, ramp_start REAL NOT NULL, stage TEXT NOT NULL, next_step REAL NOT NULL, "
               "lights TEXT NOT NULL DEFAULT '[]', player TEXT, snooze_until REAL, fade_from REAL)")
    return db


def rows(*, path=None):
    with closing(_connect(path)) as db:
        return [dict(row) for row in db.execute("SELECT * FROM wakes ORDER BY wake_at")]


def _update(row, path=None, **changes):
    """Change a row only if nobody else moved it on since it was read."""
    columns = ", ".join(f"{name} = ?" for name in changes)
    with closing(_connect(path)) as db, db:
        changed = db.execute(f"UPDATE wakes SET {columns} WHERE room = ? AND stage = ? AND wake_at = ?",  # nosec B608
                             (*changes.values(), row["room"], row["stage"], row["wake_at"])).rowcount
    if changed:
        row.update(changes)
    return bool(changed)


def _local(timestamp):
    return datetime.fromtimestamp(timestamp).astimezone()


def _when(row, now=None):
    moment = _local(row["wake_at"])
    if row["days"] != "once":
        return f"{moment:%H:%M} {DAYS[row['days']]}"
    today = _local(time() if now is None else now).date()
    day = "today" if moment.date() == today else "tomorrow" if moment.date() == today + timedelta(days=1) else f"on {moment:%A}"
    return f"{moment:%H:%M} {day}"


def active(*, now=None, path=None):
    """True while a sunrise is ramping, waking someone or snoozed: "stop" and "snooze" are for it."""
    try:
        return any(row["stage"] in ACTIVE for row in rows(path=path))
    except (OSError, sqlite3.Error):
        return False


def _line(kind):
    from declan.turn import line_freshness
    return line_freshness.pick("sunrise:" + kind, LINES[kind], topic=TOPICS[kind])


def command(request, opener, *, satellite=None, device=None, browser=False, now=None, path=None, ha=None):
    """Set, ask about, cancel or skip a sunrise; stop and snooze while one is running."""
    from declan.timers import timers
    ha = ha or (lambda api, data=None: timers.ha_json(opener, api, data=data, timeout=7))
    kind = request[0]
    now_dt = datetime.fromtimestamp(time() if now is None else now).astimezone()
    try:
        if kind == "snooze":
            return snooze(satellite, ha, now=now_dt.timestamp(), path=path)
        if kind == "set":
            _, hour, minute, days, music = request
            output = timers.resolve_output(opener, satellite, device, browser=browser)
            if output is None:
                return ExecutionResult("Ask me from the bedroom satellite, so I know which lights to use.",
                                       Outcome.UNAVAILABLE)
            wake = next_wake(hour, minute, days, now_dt)
            ramp_start = max(now_dt.timestamp(), wake - RAMP_SECONDS)
            music = _DEFAULT_MUSIC if music == "" else music
            with closing(_connect(path)) as db, db:
                db.execute("INSERT INTO wakes (room, satellite, hour, minute, days, music, wake_at, ramp_start, stage, "
                           "next_step) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'waiting', ?) ON CONFLICT(room) DO UPDATE SET "
                           "satellite = excluded.satellite, hour = excluded.hour, minute = excluded.minute, "
                           "days = excluded.days, music = excluded.music, wake_at = excluded.wake_at, "
                           "ramp_start = excluded.ramp_start, stage = 'waiting', next_step = excluded.next_step, "
                           "lights = '[]', player = NULL, snooze_until = NULL, fade_from = NULL",
                           (output[1].casefold(), output[0], hour, minute, days, music, wake, ramp_start, ramp_start))
            row = {"wake_at": wake, "days": days}
            then = "then music" if music else "no music"
            return ExecutionResult(f"Sunrise set for {_when(row, now_dt.timestamp())} in the {output[1]}. The lights start brightening at "
                                   f"{_local(ramp_start):%H:%M}, {then}.", Outcome.TIMER_SET)
        mine = _rows_for(satellite, opener, path=path)
        if kind == "ask":
            if not mine:
                return ExecutionResult("No sunrise set. You'll have to wake up the old-fashioned way.", Outcome.NO_TIMER)
            return ExecutionResult(". ".join(f"Sunrise in the {row['room']} at {_when(row, now_dt.timestamp())}" for row in mine) + ".",
                                   Outcome.TIMER_STATUS)
        if not mine:
            return ExecutionResult("There's no sunrise set.", Outcome.NO_TIMER)
        if kind == "cancel":
            for row in mine:
                _lights_off(ha, row)
                with closing(_connect(path)) as db, db:
                    db.execute("DELETE FROM wakes WHERE room = ?", (row["room"],))
            return ExecutionResult("Sunrise cancelled.", Outcome.TIMER_CANCELLED)
        if kind == "skip":
            skipped = []
            for row in mine:
                if row["days"] == "once":
                    with closing(_connect(path)) as db, db:
                        db.execute("DELETE FROM wakes WHERE room = ?", (row["room"],))
                    skipped.append(f"Cancelled the sunrise in the {row['room']}.")
                else:
                    _finish(row, now_dt.timestamp(), path=path)
                    skipped.append(f"Skipped. Next sunrise in the {row['room']} is at {_when(row, now_dt.timestamp())}.")
            return ExecutionResult(" ".join(skipped), Outcome.TIMER_ADJUSTED)
    except (OSError, ValueError, sqlite3.Error):
        return ExecutionResult("I couldn't change the sunrise just now.", Outcome.UNAVAILABLE)
    return None


def _rows_for(satellite, opener, *, path=None):
    """This satellite's room's sunrise, else all of them (browser, or asked from elsewhere)."""
    all_rows = rows(path=path)
    mine = [row for row in all_rows if satellite and row["satellite"] == satellite]
    return mine or all_rows


def stop(satellite, *, opener=None, ha=None, now=None, path=None):
    """End running sunrises: this satellite's first, otherwise every running one."""
    from declan.timers import timers
    ha = ha or (lambda api, data=None: timers.ha_json(opener, api, data=data, timeout=7))
    now = time() if now is None else now
    running = [row for row in rows(path=path) if row["stage"] in ACTIVE]
    if not running:
        return None
    chosen = [row for row in running if satellite and row["satellite"] == satellite] or running
    for row in chosen:
        _lights_off(ha, row)
        if row["player"]:
            _call(ha, "/api/services/media_player/media_pause", {"entity_id": row["player"]})
        _finish(row, now, path=path)
    return ExecutionResult(_line("stop"), Outcome.TIMER_STOPPED)


def snooze(satellite, ha, *, now=None, path=None):
    now = time() if now is None else now
    awake = [row for row in rows(path=path) if row["stage"] == "awake"]
    chosen = [row for row in awake if satellite and row["satellite"] == satellite] or awake
    if not chosen:
        if any(row["stage"] in ACTIVE for row in rows(path=path)):
            return ExecutionResult("It's not even time to get up yet. Go back to sleep.", Outcome.UNRESOLVED)
        return ExecutionResult("Nothing to snooze.", Outcome.NO_TIMER)
    for row in chosen:
        if row["player"]:
            _call(ha, "/api/services/media_player/media_pause", {"entity_id": row["player"]})
        _update(row, path=path, stage="snoozed", snooze_until=now + SNOOZE_SECONDS, next_step=now + SNOOZE_SECONDS)
    return ExecutionResult(_line("snooze"), Outcome.TIMER_ADJUSTED)


def _call(ha, api, data):
    try:
        return ha(api, data)
    except (OSError, ValueError, TimeoutError):
        return None


def _lights_off(ha, row):
    lights = [entity for entity, _ in json.loads(row["lights"] or "[]")]
    if lights and row["stage"] in ACTIVE:
        _call(ha, "/api/services/light/turn_off", {"entity_id": lights, "transition": 2})


_LIGHTS_TEMPLATE = (
    "{% set ns = namespace(lights=[]) %}"
    "{% for entity in area_entities(area_id(SATELLITE)) if entity.startswith('light.') %}"
    "{% set modes = state_attr(entity, 'supported_color_modes') or [] %}"
    "{% if states(entity) == 'off' and modes and modes | reject('in', ['onoff']) | list | count %}"
    "{% set ns.lights = ns.lights + [[entity, 'color_temp' in modes]] %}"
    "{% endif %}{% endfor %}{{ ns.lights | to_json }}"
)


def _dimmable_lights(ha, satellite):
    """[[entity, supports colour temperature]] for the room's dimmable lights that are off."""
    found = _call(ha, "/api/template", {"template": _LIGHTS_TEMPLATE.replace("SATELLITE", json.dumps(satellite))})
    if not isinstance(found, list):
        return []
    return [[row[0], bool(row[1])] for row in found
            if isinstance(row, list) and len(row) == 2 and isinstance(row[0], str)
            and re.fullmatch(r"light\.[a-z0-9_]+", row[0])]


def _brighten(ha, row, fraction, transition):
    lights = json.loads(row["lights"] or "[]")
    if not lights:
        return
    fraction = min(1.0, max(0.0, fraction))
    data = {"brightness_pct": max(1, round(100 * fraction)), "transition": max(1, round(transition))}
    warm = [entity for entity, temp in lights if temp]
    plain = [entity for entity, temp in lights if not temp]
    if warm:
        kelvin = round(KELVIN_START + (KELVIN_END - KELVIN_START) * fraction)
        _call(ha, "/api/services/light/turn_on", {"entity_id": warm, **data, "color_temp_kelvin": kelvin})
    if plain:
        _call(ha, "/api/services/light/turn_on", {"entity_id": plain, **data})


def _finish(row, now, *, path=None):
    """End this morning: a one-off is deleted, a schedule moves to its next day."""
    if row["days"] == "once":
        with closing(_connect(path)) as db, db:
            db.execute("DELETE FROM wakes WHERE room = ? AND wake_at = ?", (row["room"], row["wake_at"]))
        return
    after = datetime.fromtimestamp(max(now, row["wake_at"])).astimezone()
    wake = next_wake(row["hour"], row["minute"], row["days"], after)
    _update(row, path=path, stage="waiting", wake_at=wake, ramp_start=wake - RAMP_SECONDS,
            next_step=wake - RAMP_SECONDS, lights="[]", player=None, snooze_until=None, fade_from=None)


class MusicAssistant:
    """The bits of Declan's music code the sunrise needs, for the room's satellite."""

    def __init__(self, music_module, connect, read_inventory):
        self.music, self.connect, self.read_inventory = music_module, connect, read_inventory

    def target(self, satellite):
        """(this room's player or None, name of another room already playing or None)."""
        from declan.ha import ha_inventory
        connection = self.connect()
        inventory = ha_inventory.InventoryResult.coerce(self.read_inventory(connection)).inventory or []
        destinations, players = self.music.music_players(inventory, origin=satellite)
        areas = {self.music.room_key(row["declan_area"]) for row in inventory
                 if isinstance(row, dict) and (row.get("entity_id") == satellite)
                 and isinstance(row.get("declan_area"), str) and row["declan_area"].strip()}
        player = destinations.get(areas.pop()) if len(areas) == 1 else None
        members = set(((players.get(player) or {}).get("attributes") or {}).get("group_members") or ())
        for entity, row in players.items():
            if entity == player or entity in members or row.get("state") != "playing":
                continue
            group = set((row.get("attributes") or {}).get("group_members") or ())
            if player in group:
                continue
            name = (row.get("attributes") or {}).get("friendly_name") or row.get("declan_area") or entity
            return player, str(name)
        return player, None

    def play(self, title, satellite):
        command = self.music.parse("play " + title) or (None, title, "spotify")
        return self.music.play_result((None, command[1], command[2]), self.connect(), self.read_inventory,
                                      origin=satellite)


def _wake(row, now, ha, music, path=None):
    """Full brightness, good morning, and music fading in if it won't hijack another room."""
    if not _update(row, path=path, stage="awake", fade_from=now, next_step=now + STEP_SECONDS):
        return
    _brighten(ha, row, 1.0, 2)
    words = [_line("wake")]
    player = None
    if row["music"] and music is not None:
        try:
            player, busy = music.target(row["satellite"])
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            player, busy = None, None
        if busy:
            words.append(f"Music's already playing in the {busy}, so I've left it alone.")
            player = None
        elif player is None:
            words.append("I couldn't find a speaker in here, so no music.")
    _call(ha, "/api/services/assist_satellite/announce",
          {"entity_id": row["satellite"], "message": " ".join(words), "preannounce": True})
    if player:
        _call(ha, "/api/services/media_player/volume_set", {"entity_id": player, "volume_level": VOLUME_START})
        try:
            result = music.play(row["music"], row["satellite"])
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            result = None
        if result is None or getattr(result, "outcome", None) not in {
                Outcome.CONFIRMED, Outcome.STARTED, Outcome.REQUESTED, Outcome.REPORTED_SUCCESS}:
            player = None
    _update(row, path=path, player=player)


def due(opener=None, *, music=None, now=None, path=None, ha=None):
    """Move every sunrise along. Called every few seconds in the background."""
    from declan.timers import timers
    ha = ha or (lambda api, data=None: timers.ha_json(opener, api, data=data, timeout=7))
    now = time() if now is None else now
    if not Path(PATH if path is None else path).exists():
        return  # no sunrise has ever been set
    for row in rows(path=path):
        try:
            _advance(row, now, ha, music, path=path)
        except (OSError, ValueError, sqlite3.Error):
            continue


def _advance(row, now, ha, music, *, path=None):
    stage = row["stage"]
    if stage == "waiting":
        if now >= row["wake_at"] + LATE_SECONDS:
            _finish(row, now, path=path)  # Declan was down: never switch lights on late
            return
        if now < row["ramp_start"]:
            return
        lights = json.dumps(_dimmable_lights(ha, row["satellite"]))
        if not _update(row, path=path, stage="ramp", lights=lights, next_step=now):
            return
        stage = "ramp"
    if stage == "ramp":
        if now >= row["wake_at"]:
            _wake(row, now, ha, music, path=path)
        elif now >= row["next_step"]:
            span = max(1.0, row["wake_at"] - row["ramp_start"])
            step_end = min(row["wake_at"], now + STEP_SECONDS)
            _brighten(ha, row, (step_end - row["ramp_start"]) / span, step_end - now)
            _update(row, path=path, next_step=now + STEP_SECONDS)
        return
    if stage == "snoozed":
        if now >= (row["snooze_until"] or 0):
            _call(ha, "/api/services/assist_satellite/announce",
                  {"entity_id": row["satellite"], "message": "Snooze is over. Up you get.", "preannounce": True})
            if row["player"]:
                _call(ha, "/api/services/media_player/volume_set", {"entity_id": row["player"], "volume_level": VOLUME_START})
                _call(ha, "/api/services/media_player/media_play", {"entity_id": row["player"]})
            _update(row, path=path, stage="awake", fade_from=now, next_step=now + STEP_SECONDS)
        return
    if stage == "awake":
        if now >= (row["fade_from"] or row["wake_at"]) + AWAKE_SECONDS:
            _finish(row, now, path=path)
        elif now >= row["next_step"]:
            if row["player"]:
                fraction = min(1.0, (now - (row["fade_from"] or now)) / FADE_SECONDS)
                volume = round(VOLUME_START + (VOLUME_END - VOLUME_START) * fraction, 3)
                _call(ha, "/api/services/media_player/volume_set", {"entity_id": row["player"], "volume_level": volume})
            _update(row, path=path, next_step=now + STEP_SECONDS)
