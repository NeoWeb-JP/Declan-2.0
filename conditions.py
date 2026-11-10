"""Read-only weather and local-time queries."""

import json
import math
import os
import re
from datetime import datetime
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


HOME_WEATHER = re.compile(
    r"(?:what(?:'s| is) (?:the )?|how(?:'s| is) (?:the )?)"
    r"(?P<kind>weather(?: like)?|(?:current )?temperature)"
    r"(?: (?P<where>outside|outdoors|at home))?"
)
PLACE_QUESTION = re.compile(
    r"what(?:'s| is) (?:the )?(?P<kind>(?:current )?(?:temperature|time)|weather(?: like)?) "
    r"in (?P<place>.+)"
)
INSIDE = {"what's the temperature inside", "what is the temperature inside",
          "what's the indoor temperature", "what is the indoor temperature"}

HA_CONDITIONS = {
    "clear-night": "clear", "cloudy": "cloudy", "exceptional": "unusual",
    "fog": "foggy", "hail": "hailing", "lightning": "stormy",
    "lightning-rainy": "stormy with rain", "partlycloudy": "partly cloudy",
    "pouring": "raining heavily", "rainy": "raining", "snowy": "snowing",
    "snowy-rainy": "snowing and raining", "sunny": "sunny",
    "windy": "windy", "windy-variant": "windy and cloudy",
}
WMO_CONDITIONS = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "foggy", 51: "drizzling", 53: "drizzling",
    55: "drizzling", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "raining lightly", 63: "raining", 65: "raining heavily",
    66: "freezing rain", 67: "freezing rain", 71: "snowing lightly",
    73: "snowing", 75: "snowing heavily", 77: "snow grains",
    80: "light rain showers", 81: "rain showers", 82: "heavy rain showers",
    85: "snow showers", 86: "heavy snow showers", 95: "thunderstorms",
    96: "thunderstorms with hail", 99: "thunderstorms with hail",
}


def read_json(opener, url, headers=None, timeout=3):
    try:
        with opener.open(Request(url, headers=headers or {}), timeout=timeout) as response:
            payload = json.loads(response.read(1024 * 1024))
        return payload if isinstance(payload, dict) else {}
    except HTTPError as error:
        error.close()
    except (OSError, ValueError):
        pass
    return {}


def reading(value, unit):
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    suffix = {"°C": " degrees Celsius", "°F": " degrees Fahrenheit"}.get(
        unit if isinstance(unit, str) else None, " degrees"
    )
    return f"{round(value, 1):g}{suffix}"


def home_temperatures(opener, *, indoors_only=False, outdoors_only=False, report=False):
    url = os.environ.get("DECLAN_HA_URL", "").strip().rstrip("/")
    token = os.environ.get("DECLAN_HA_TOKEN", "").strip()
    try:
        parsed = urlsplit(url)
        configured = (token and parsed.scheme in {"http", "https"} and parsed.hostname
                      and not any((parsed.username, parsed.password, parsed.query, parsed.fragment)))
    except ValueError:
        configured = False
    if not configured:
        return "The Home Assistant weather and temperature readings aren't configured.", "not_configured"
    headers = {"Authorization": f"Bearer {token}"}
    weather = os.environ.get("DECLAN_WEATHER_ENTITY", "weather.forecast_home").strip()
    indoor = os.environ.get("DECLAN_INDOOR_TEMPERATURE_ENTITY", "climate.home").strip()

    def state(entity, pattern):
        if not re.fullmatch(pattern, entity):
            return {}
        result = read_json(opener, f"{url}/api/states/{entity}", headers, timeout=2)
        return result if result.get("state") not in (None, "unknown", "unavailable") else {}

    outside_state = state(weather, r"weather\.[a-z0-9_]+") if not indoors_only else {}
    inside_state = state(indoor, r"(?:climate|sensor)\.[a-z0-9_]+") if not outdoors_only else {}
    outside_attrs = outside_state.get("attributes") or {}
    inside_attrs = inside_state.get("attributes") or {}
    if not isinstance(outside_attrs, dict):
        outside_attrs = {}
    if not isinstance(inside_attrs, dict):
        inside_attrs = {}
    outside_unit = outside_attrs.get("temperature_unit")
    inside_unit = inside_attrs.get("temperature_unit") or inside_attrs.get("unit_of_measurement") or outside_unit
    inside_value = inside_attrs.get("current_temperature")
    if indoor.startswith("sensor.") and inside_state:
        try:
            inside_value = float(inside_state["state"])
        except (ValueError, TypeError):
            inside_value = None
    outside = reading(outside_attrs.get("temperature"), outside_unit)
    inside = reading(inside_value, inside_unit)
    if indoors_only:
        return (f"It's {inside} inside.", "confirmed") if inside else ("The indoor temperature is unavailable.", "unavailable")
    reply = f"It's {outside} outside." if outside else "The outside temperature is unavailable."
    if outdoors_only:
        return reply, "confirmed" if outside else "unavailable"
    condition = HA_CONDITIONS.get(outside_state.get("state")) if report else None
    if condition:
        reply = f"Outside, it's {condition} and {outside}." if outside else f"Outside, it's {condition}. {reply}"
    elif report:
        reply = f"I couldn't verify the outside conditions. {reply}"
    reply += f" Inside, it's {inside}." if inside else " The indoor temperature is unavailable."
    return reply, "confirmed" if outside and inside and (condition or not report) else "partial" if outside or inside or condition else "unavailable"


def find_place(opener, query):
    city, _, qualifier = re.sub(r"\s+in\s+", ", ", query, count=1).partition(",")
    city, qualifier = city.strip(), qualifier.strip()
    if not city or len(query) > 100:
        return None, "Please give me a city and, if needed, its country."
    country = {"uk": "gb", "united kingdom": "gb", "south africa": "za"}.get(qualifier)
    witbank = city == "witbank" and (not qualifier or country == "za")
    search_name = "emalahleni" if witbank else city
    if witbank:
        country = "za"
    args = {"name": search_name if country or not qualifier else f"{search_name}, {qualifier}",
            "count": 20, "language": "en"}
    if country:
        args["countryCode"] = country.upper()
    data = read_json(opener, "https://geocoding-api.open-meteo.com/v1/search?" + urlencode(args))
    if not data:
        return None, "The location service didn't return a result I could verify."
    rows = data.get("results", [])
    if not isinstance(rows, list):
        rows = []
    candidates = [row for row in rows if isinstance(row, dict) and isinstance(row.get("name"), str)
                  and str(row.get("feature_code", "")).startswith("PPL")
                  and (not country or str(row.get("country_code", "")).lower() == country)]
    candidates = [row for row in candidates if row["name"].casefold() == search_name]
    if not qualifier and len(candidates) > 1:
        preferred = os.environ.get("DECLAN_DEFAULT_COUNTRY", "GB").upper()
        domestic = [row for row in candidates if row.get("country_code") == preferred]
        if len(domestic) == 1:
            candidates = domestic
    if len(candidates) == 1:
        location = candidates[0]
        if witbank and location["name"].casefold() == search_name:
            location = {**location, "name": "Witbank"}
        return location, None
    if candidates:
        return None, f"Which {city.title()} do you mean? Please include the country or region."
    return None, f"I couldn't find {query.title()} in the location service."


def handle(phrase, opener):
    phrase = phrase.replace("’", "'")
    phrase = re.sub(r"^what time is it in ", "what is the time in ", phrase)
    place = PLACE_QUESTION.fullmatch(phrase)
    home = HOME_WEATHER.fullmatch(phrase)
    if not place and not home and phrase not in INSIDE:
        return None
    if not place:
        report = bool(home and home["kind"].startswith("weather"))
        outdoors_only = bool(home and not report and home["where"] in {"outside", "outdoors"})
        reply, outcome = home_temperatures(
            opener, indoors_only=phrase in INSIDE, outdoors_only=outdoors_only, report=report
        )
        return reply, outcome, "weather"
    kind, query = place.group("kind", "place")
    category = "time" if kind.endswith("time") else "weather"
    location, error = find_place(opener, query)
    if location is None:
        return error, "unresolved", category
    name = ", ".join(value for value in (location["name"], location.get("country")) if isinstance(value, str) and value)
    if category == "time":
        try:
            clock = datetime.now(ZoneInfo(location["timezone"])).strftime("%H:%M")
        except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError):
            return f"I couldn't verify the local time in {name}.", "unavailable", category
        return f"It's {clock} in {name}.", "confirmed", category
    report = kind.startswith("weather")
    requested = "current weather" if report else "current temperature"
    try:
        coordinates = {key: float(location[key]) for key in ("latitude", "longitude")}
    except (KeyError, TypeError, ValueError):
        return f"I couldn't verify the {requested} in {name}.", "unavailable", category
    fields = "temperature_2m,weather_code" if report else "temperature_2m"
    data = read_json(opener, "https://api.open-meteo.com/v1/forecast?" + urlencode(
        {**coordinates, "current": fields, "temperature_unit": "celsius"}))
    current = data.get("current")
    current = current if isinstance(current, dict) else {}
    temperature = reading(current.get("temperature_2m"), "°C")
    code = current.get("weather_code")
    condition = WMO_CONDITIONS.get(code) if report and type(code) is int else None
    if condition and temperature:
        return f"In {name}, it's {condition} and {temperature}.", "confirmed", category
    if condition:
        return f"In {name}, it's {condition}. The temperature is unavailable.", "partial", category
    if temperature is None:
        return f"I couldn't verify the {requested} in {name}.", "unavailable", category
    if report:
        return f"It's {temperature} in {name}. I couldn't verify the conditions.", "partial", category
    return f"It's {temperature} in {name}.", "confirmed", category
