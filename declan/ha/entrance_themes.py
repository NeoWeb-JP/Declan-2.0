"""Entrance themes (FUT-46, #834).

When someone gets home, their theme song plays for about ten seconds on the
entrance satellite.

- Arrivals come from Home Assistant ``person`` entities (their phone), never
  from voice. A person who appears for the first time, or after HA restarts,
  is only recorded, so nobody gets a theme just because Declan started up.
- A real arrival: away for at least 10 minutes, and no theme for them in the
  last 30 minutes, so a phone flicking between home and away doesn't replay it.
- The theme is a short clip in Home Assistant's media (a media-source:// ID,
  e.g. media-source://media_source/local/themes/jaco.mp3) announced on the
  satellite, not Spotify, so the household's Spotify stream is untouched.
- Never during quiet hours (23:00 to 07:00) or Guest mode, and not while music
  is playing in the entrance room, so playing music is never stopped or
  changed. A skipped arrival isn't played later.
- Opt-in per person, in Settings -> Household -> Entrance themes, where each
  theme can be switched off or tried out.
"""
import json
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from time import time

PATH = Path(__file__).resolve().parents[2] / ".data" / "entrance-themes.sqlite3"
MIN_AWAY_SECONDS = 10 * 60
REPEAT_SECONDS = 30 * 60
PERSON = re.compile(r"person\.[a-z0-9_]{1,80}")
SATELLITE = re.compile(r"assist_satellite\.[a-z0-9_]{1,80}")
MEDIA = re.compile(r"media-source://[\x21-\x7e]{1,280}")
_UNKNOWN = frozenset({"unknown", "unavailable", ""})

_TEMPLATE = (
    "{% set ns = namespace(people=[]) %}"
    "{% for person in states.person %}"
    "{% set ns.people = ns.people + [[person.entity_id, person.state, person.name]] %}"
    "{% endfor %}"
    "{% set satellite = SATELLITE %}"
    "{% set busy = satellite and (area_entities(area_id(satellite)) | select('match', '^media_player[.]') "
    "| select('is_state', 'playing') | list | count > 0) %}"
    "{{ {'people': ns.people, 'guest': states(GUEST), 'busy': busy} | to_json }}"
)


def _connect(path=None):
    path = Path(PATH if path is None else path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS people (person TEXT PRIMARY KEY, name TEXT NOT NULL, media_id TEXT NOT NULL "
               "DEFAULT '', enabled INTEGER NOT NULL DEFAULT 0, state TEXT, left_at REAL, played_at REAL)")
    db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    return db


def satellite(*, path=None):
    """The satellite themes play on: Settings first, then DECLAN_ENTRANCE_SATELLITE."""
    saved = None
    if Path(PATH if path is None else path).exists():
        with closing(_connect(path)) as db:
            row = db.execute("SELECT value FROM settings WHERE key = 'satellite'").fetchone()
            saved = row[0] if row else None
    value = saved if saved is not None else os.environ.get("DECLAN_ENTRANCE_SATELLITE", "").strip()
    return value if SATELLITE.fullmatch(value or "") else ""


def save_satellite(value, *, path=None):
    value = (value or "").strip() if isinstance(value, str) else None
    if value is None or (value and not SATELLITE.fullmatch(value)):
        raise ValueError("Use an assist_satellite entity, like assist_satellite.hallway.")
    with closing(_connect(path)) as db, db:
        db.execute("INSERT INTO settings VALUES ('satellite', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                   (value,))
    return value


def save_theme(person, media_id, enabled, *, path=None):
    if not isinstance(person, str) or not PERSON.fullmatch(person):
        raise ValueError("That isn't a Home Assistant person.")
    media_id = media_id.strip() if isinstance(media_id, str) else None
    if media_id is None or (media_id and not MEDIA.fullmatch(media_id)):
        raise ValueError("Use a media-source:// clip from Home Assistant's Media, e.g. "
                         "media-source://media_source/local/themes/jaco.mp3.")
    if type(enabled) is not bool or (enabled and not media_id):
        raise ValueError("Choose a clip before switching the theme on.")
    with closing(_connect(path)) as db, db:
        changed = db.execute("UPDATE people SET media_id = ?, enabled = ? WHERE person = ?",
                             (media_id, int(enabled), person)).rowcount
    if not changed:
        raise ValueError("Declan hasn't seen that person in Home Assistant yet.")
    return {"person": person, "media_id": media_id, "enabled": enabled}


def listing(*, path=None):
    people = []
    if Path(PATH if path is None else path).exists():
        with closing(_connect(path)) as db:
            people = [{"person": row["person"], "name": row["name"], "media_id": row["media_id"],
                       "enabled": bool(row["enabled"]), "home": row["state"] == "home", "played_at": row["played_at"]}
                      for row in db.execute("SELECT * FROM people ORDER BY name")]
    return {"satellite": satellite(path=path), "people": people}


def _play(ha, entrance, media_id):
    ha("/api/services/assist_satellite/announce",
       {"entity_id": entrance, "media_id": media_id, "preannounce": False})


def try_theme(person, ha, *, path=None):
    """Settings' "Try it" button: play one person's clip now."""
    entrance = satellite(path=path)
    if not entrance:
        raise ValueError("Choose the entrance satellite first.")
    with closing(_connect(path)) as db:
        row = db.execute("SELECT media_id FROM people WHERE person = ?", (person,)).fetchone()
    if row is None or not row[0]:
        raise ValueError("That person doesn't have a clip yet.")
    _play(ha, entrance, row[0])


def due_with_opener(opener):
    """Background entry point: Home Assistant calls go through Declan's usual HA connection."""
    from declan.timers import timers
    return due(lambda api, data=None: timers.ha_json(opener, api, data=data, timeout=5))


def due(ha, *, now=None, quiet=None, guest_entity=None, path=None):
    """Check who's home, and play a theme for each real arrival. Called every few seconds."""
    now = time() if now is None else now
    entrance = satellite(path=path)
    if guest_entity is None:
        from declan.ha import household_entities
        try:
            guest_entity = household_entities.guest_mode()
        except ValueError:
            guest_entity = "input_boolean.guest_mode"
    template = _TEMPLATE.replace("SATELLITE", json.dumps(entrance or "")).replace("GUEST", json.dumps(guest_entity))
    try:
        house = ha("/api/template", {"template": template})
    except (OSError, ValueError, TimeoutError):
        return []  # Home Assistant isn't there (or isn't configured): nothing to do
    if not isinstance(house, dict) or not isinstance(house.get("people"), list):
        return []
    if quiet is None:
        from declan.turn import personality_policy
        quiet = personality_policy.quiet_hours()
    # Unknown Guest Mode counts as on: no surprise music for visitors.
    blocked = quiet or house.get("guest") != "off" or house.get("busy") is not False or not entrance
    played = []
    with closing(_connect(path)) as db, db:
        for entry in house["people"]:
            if not (isinstance(entry, list) and len(entry) == 3 and all(isinstance(value, str) for value in entry)
                    and PERSON.fullmatch(entry[0])):
                continue
            person, state, name = entry
            if state in _UNKNOWN:
                continue  # HA restarting or a phone dropping out isn't an arrival or a departure
            row = db.execute("SELECT * FROM people WHERE person = ?", (person,)).fetchone()
            if row is None:
                db.execute("INSERT INTO people (person, name, state, left_at) VALUES (?, ?, ?, ?)",
                           (person, name[:80], state, None if state == "home" else now))
                continue
            if row["name"] != name[:80]:
                db.execute("UPDATE people SET name = ? WHERE person = ?", (name[:80], person))
            previous = row["state"]
            if state == previous:
                continue
            if state != "home":
                if previous == "home":
                    db.execute("UPDATE people SET state = ?, left_at = ? WHERE person = ?", (state, now, person))
                else:
                    db.execute("UPDATE people SET state = ? WHERE person = ?", (state, person))
                continue
            db.execute("UPDATE people SET state = 'home' WHERE person = ?", (person,))
            arrived = (previous is not None and row["left_at"] is not None
                       and now - row["left_at"] >= MIN_AWAY_SECONDS
                       and (row["played_at"] is None or now - row["played_at"] >= REPEAT_SECONDS))
            if not arrived or not row["enabled"] or not row["media_id"]:
                continue
            # This arrival is used up whether it plays or not: never played later.
            db.execute("UPDATE people SET played_at = ? WHERE person = ?", (now, person))
            if not blocked:
                played.append((person, row["media_id"]))
    for person, media_id in played:
        try:
            _play(ha, entrance, media_id)
        except (OSError, ValueError, TimeoutError):
            continue
    return [person for person, _ in played]
