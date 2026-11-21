"""Where Declan reads household information from (#834 P2).

Settings -> Household -> Car, briefing and phones. A value saved there wins,
then the environment variable, then the default.

car_name: what Declan calls the car ("the Peugeot"). Default "the car".
car_battery: the car's battery sensor (e.g. sensor.vr3ukzkxzmj747298_battery).
    Empty: Declan answers from the Pod Point charger alone.
car_in_sunrise: say one line about the car in the sunrise wake-up's good
    morning (FUT-45). Default on; needs the charger or battery sensor.
briefing: what the morning briefing covers (FUT-29), comma-separated from
    weather, calendar, car, bins. Default all four; empty turns it off.
calendars: comma-separated calendar entities for the briefing. Empty: every
    calendar except the bins one.
bins: the bin collection calendar or sensor (calendar.bins, sensor.recycling).
    Empty: no bin line.
briefing_in_good_morning: add the briefing to the Good Morning routine's reply.

The Pod Point charger itself is found automatically (the pod_point integration).
"""
import json
import os
import re
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / ".data" / "house-info.json"
ENVIRONMENT = {"car_name": "DECLAN_CAR_NAME", "car_battery": "DECLAN_CAR_BATTERY_ENTITY",
               "car_in_sunrise": "DECLAN_CAR_IN_SUNRISE", "briefing": "DECLAN_BRIEFING",
               "calendars": "DECLAN_BRIEFING_CALENDARS", "bins": "DECLAN_BINS_ENTITY",
               "briefing_in_good_morning": "DECLAN_BRIEFING_IN_GOOD_MORNING"}
DEFAULTS: dict[str, object] = {"car_name": "the car", "car_battery": "", "car_in_sunrise": True,
                               "briefing": "weather,calendar,car,bins", "calendars": "", "bins": "",
                               "briefing_in_good_morning": True}
BRIEFING_ITEMS = ("weather", "calendar", "car", "bins")
_CALENDAR = re.compile(r"calendar\.[a-z0-9_]{1,100}")
_BINS = re.compile(r"(?:calendar|sensor)\.[a-z0-9_]{1,100}")
_ON = frozenset({"1", "true", "yes", "on"})
_OFF = frozenset({"0", "false", "no", "off"})
_SENSOR = re.compile(r"sensor\.[a-z0-9_]{1,100}")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 '\-]{0,29}")


def _valid(key, value):
    if key == "car_name":
        return isinstance(value, str) and bool(_NAME.fullmatch(value))
    if key == "car_battery":
        return isinstance(value, str) and (value == "" or bool(_SENSOR.fullmatch(value)))
    if key in {"car_in_sunrise", "briefing_in_good_morning"}:
        return type(value) is bool
    if key == "briefing":
        return isinstance(value, str) and len(value) <= 60 and all(
            item in BRIEFING_ITEMS for item in split(value))
    if key == "calendars":
        return isinstance(value, str) and len(value) <= 600 and all(
            _CALENDAR.fullmatch(item) for item in split(value))
    if key == "bins":
        return isinstance(value, str) and (value == "" or bool(_BINS.fullmatch(value)))
    return False


def split(value):
    """"a, b,,c" -> ["a", "b", "c"]."""
    return [item.strip() for item in value.split(",") if item.strip()] if isinstance(value, str) else []


def _from_environment(key):
    raw = os.environ.get(ENVIRONMENT[key], "").strip()
    if type(DEFAULTS[key]) is bool:
        return True if raw.casefold() in _ON else False if raw.casefold() in _OFF else None
    if key in {"briefing", "calendars"}:
        raw = ",".join(split(raw.casefold() if key == "briefing" else raw))
    return raw if raw and _valid(key, raw) else None


def _saved(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def listing(path=None):
    saved = _saved(PATH if path is None else path)
    settings, sources = {}, {}
    for key, default in DEFAULTS.items():
        environment = _from_environment(key)
        if key in saved and _valid(key, saved[key]):
            settings[key], sources[key] = saved[key], "saved"
        elif environment is not None:
            settings[key], sources[key] = environment, "environment"
        else:
            settings[key], sources[key] = default, "default"
    return {"settings": settings, "sources": sources}


def save(payload, path=None):
    """Save the keys sent; the others are kept."""
    path = Path(PATH if path is None else path)
    if isinstance(payload, dict):
        payload = {key: ",".join(split(value)) if key in {"briefing", "calendars"} and isinstance(value, str) else value
                   for key, value in payload.items()}
    if (not isinstance(payload, dict) or not payload or not set(payload) <= set(DEFAULTS)
            or not all(_valid(key, value) for key, value in payload.items())):
        raise ValueError("Use a car name of up to 30 letters or numbers, a sensor entity for the car battery "
                         "(like sensor.car_battery) or nothing, briefing items from weather, calendar, car and bins, "
                         "calendar entities for the briefing, and a calendar or sensor for the bins.")
    kept = {key: value for key, value in _saved(path).items() if key in DEFAULTS and _valid(key, value)}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps({**kept, **payload}, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return listing(path)


def get(key, path=None):
    return listing(path)["settings"][key]
