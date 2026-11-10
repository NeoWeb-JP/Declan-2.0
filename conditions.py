"""Read-only weather and local-time queries."""

import json
import math
import os
import re
from datetime import date, datetime, timedelta
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

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
PERIOD = r"today|tomorrow|this weekend|(?:on )?(?:" + "|".join(WEEKDAYS) + r")"
FORECAST = re.compile(
    r"(?P<kind>(?:(?:what(?:'s| is| will be)|how(?:'s| is)|give me|show me) (?:the )?)?"
    r"(?:weather forecast|forecast|weather(?: like)?|temperature)|"
    r"what will the (?:weather|temperature) be(?: like)?|will it rain)"
    rf"(?: (?:(?:for |at home |outside )?(?P<first>{PERIOD})(?: in (?P<after>.+))?|"
    rf"in (?P<before>.+?) (?:for )?(?P<last>{PERIOD})|in (?P<place_only>.+)))?"
)
FORECAST_FIELDS = ("weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_probability_max")
FOLLOW_UP = re.compile(
    rf"(?:(?:what|how) about |and )(?:(?P<day>{PERIOD})(?: in (?P<day_place>.+))?|"
    r"in (?P<place>.+)|(?P<home>at home|home|outside))"
)

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


def read_json(opener, url, headers=None, timeout=3, *, data=None):
    try:
        with opener.open(Request(url, headers=headers or {}, data=data), timeout=timeout) as response:
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


def ha_connection():
    url = os.environ.get("DECLAN_HA_URL", "").strip().rstrip("/")
    token = os.environ.get("DECLAN_HA_TOKEN", "").strip()
    try:
        parsed = urlsplit(url)
        configured = (token and parsed.scheme in {"http", "https"} and parsed.hostname
                      and not any((parsed.username, parsed.password, parsed.query, parsed.fragment)))
    except ValueError:
        configured = False
    return (url, {"Authorization": f"Bearer {token}"}) if configured else None


def home_temperatures(opener, *, indoors_only=False, outdoors_only=False, report=False):
    connection = ha_connection()
    if not connection:
        return "The Home Assistant weather and temperature readings aren't configured.", "not_configured"
    url, headers = connection
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


def place_coordinates(location):
    latitude, longitude = location.get("latitude"), location.get("longitude")
    if (type(latitude) in (int, float) and -90 <= latitude <= 90
            and type(longitude) in (int, float) and -180 <= longitude <= 180):
        return latitude, longitude
    return None


def nearest_place(opener, candidates):
    connection = ha_connection()
    if connection:
        url, headers = connection
        home = place_coordinates(read_json(opener, f"{url}/api/config", headers, timeout=1))
        if home:
            home_lat, home_lon = map(math.radians, home)
            distances = []
            for candidate in candidates:
                coordinates = place_coordinates(candidate)
                if coordinates:
                    lat, lon = map(math.radians, coordinates)
                    distance = (math.sin((lat - home_lat) / 2) ** 2
                                + math.cos(home_lat) * math.cos(lat) * math.sin((lon - home_lon) / 2) ** 2)
                    distances.append((distance, candidate))
            distances.sort(key=lambda entry: entry[0])
            if distances and (len(distances) == 1 or distances[0][0] != distances[1][0]):
                return distances[0][1]
            if distances:
                return None
    preferred = os.environ.get("DECLAN_DEFAULT_COUNTRY", "GB").upper()
    domestic = [row for row in candidates if row.get("country_code") == preferred]
    return domestic[0] if len(domestic) == 1 else None


def place_name(location):
    return ", ".join(dict.fromkeys(
        value for key in ("name", "display_region", "country")
        if isinstance(value := location.get(key), str) and value
    ))


def find_place(opener, query):
    city, _, qualifier = re.sub(r"\s+in\s+", ", ", query, count=1).partition(",")
    city, qualifier = city.strip(), qualifier.strip()
    countries = {"uk": "gb", "united kingdom": "gb", "south africa": "za", "australia": "au"}
    if not qualifier:
        for suffix in countries:
            if city.endswith(" " + suffix):
                city, qualifier = city[: -len(suffix) - 1], suffix
                break
    if not city or len(query) > 100:
        return None, "Please give me a city and, if needed, its country."
    country = countries.get(qualifier)
    witbank = city == "witbank" and (not qualifier or country == "za")
    sydney = city in {"sydney", "sidney"} and (not qualifier or country in {"gb", "au"})
    british_sydney = sydney and country != "au"
    search_name = "emalahleni" if witbank else "sydney" if sydney else city
    if witbank:
        country = "za"
    if british_sydney:
        country = "gb"
    args = {"name": search_name if country or not qualifier else f"{search_name}, {qualifier}",
            "count": 100, "language": "en"}
    if country:
        args["countryCode"] = country.upper()
    data = read_json(opener, "https://geocoding-api.open-meteo.com/v1/search?" + urlencode(args))
    rows = data.get("results", [])
    if not isinstance(rows, list):
        rows = []
    candidates = [row for row in rows if isinstance(row, dict) and isinstance(row.get("name"), str)
                  and (str(row.get("feature_code", "")).startswith("PPL")
                       or row.get("feature_code") == "LCTY")
                  and (not country or str(row.get("country_code", "")).lower() == country)]
    candidates = [row for row in candidates if row["name"].casefold() == search_name]
    if british_sydney and not candidates:
        # Sydney in Cheshire is GeoNames locality 13269925, which may be absent from search.
        return {"name": "Sydney", "display_region": "Cheshire", "country": "United Kingdom",
                "latitude": 53.10316, "longitude": -2.41996, "timezone": "Europe/London"}, None
    if not data:
        return None, "The location service didn't return a result I could verify."
    location = candidates[0] if len(candidates) == 1 else None
    if not qualifier and len(candidates) > 1:
        location = nearest_place(opener, candidates)
    elif sydney and country == "au" and len(candidates) > 1:
        capitals = [row for row in candidates if row.get("feature_code") == "PPLA"]
        if len(capitals) == 1:
            location = capitals[0]
    if location:
        if witbank:
            location = {**location, "name": "Witbank"}
        if british_sydney or sum(row.get("country_code") == location.get("country_code")
                                 for row in candidates) > 1:
            region = location.get("admin2") or ("Cheshire" if british_sydney else location.get("admin1"))
            location = {**location, "display_region": region}
        return location, None
    if candidates:
        return None, f"Which {city.title()} do you mean? Please include the country or region."
    return None, f"I couldn't find {query.title()} in the location service."


def forecast_dates(today, period):
    if period == "today":
        return [today]
    if period == "tomorrow":
        return [today + timedelta(days=1)]
    if period == "this weekend":
        if today.weekday() == 6:
            return [today]
        saturday = today + timedelta(days=(5 - today.weekday()) % 7)
        return [saturday, saturday + timedelta(days=1)]
    weekday = WEEKDAYS.index(period.removeprefix("on "))
    return [today + timedelta(days=(weekday - today.weekday()) % 7)]


def home_forecast(opener):
    connection = ha_connection()
    entity = os.environ.get("DECLAN_WEATHER_ENTITY", "weather.forecast_home").strip()
    if not connection or not re.fullmatch(r"weather\.[a-z0-9_]+", entity):
        return {}, None, None
    url, headers = connection
    config = read_json(opener, f"{url}/api/config", headers, timeout=2)
    zone = config.get("time_zone")
    units = config.get("unit_system")
    unit = units.get("temperature") if isinstance(units, dict) else None
    try:
        timezone = ZoneInfo(zone)
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        return {}, None, unit
    state = read_json(opener, f"{url}/api/states/{entity}", headers, timeout=1)
    attrs = state.get("attributes")
    if isinstance(attrs, dict):
        unit = attrs.get("temperature_unit") or unit
    data = read_json(
        opener, f"{url}/api/services/weather/get_forecasts?return_response",
        {**headers, "Content-Type": "application/json"}, timeout=2,
        data=json.dumps({"entity_id": entity, "type": "daily"}).encode(),
    )
    payload = data.get("service_response")
    result = payload.get(entity) if isinstance(payload, dict) else None
    rows = result.get("forecast") if isinstance(result, dict) else None
    forecast = {}
    for row in rows if isinstance(rows, list) else ():
        if not isinstance(row, dict):
            continue
        try:
            stamp = datetime.fromisoformat(row.get("datetime"))
            day = stamp.astimezone(timezone).date() if stamp.tzinfo else stamp.date()
        except (TypeError, ValueError):
            continue
        condition = row.get("condition")
        forecast[day] = (HA_CONDITIONS.get(condition) if isinstance(condition, str) else None,
                         row.get("temperature"), row.get("templow"), row.get("precipitation_probability"))
    return forecast, datetime.now(timezone).date(), unit


def place_forecast(opener, location):
    try:
        coordinates = {key: float(location[key]) for key in ("latitude", "longitude")}
        timezone = ZoneInfo(location["timezone"])
    except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError):
        return {}, None, "°C"
    data = read_json(opener, "https://api.open-meteo.com/v1/forecast?" + urlencode(
        {**coordinates, "daily": ",".join(FORECAST_FIELDS), "timezone": location["timezone"],
         "forecast_days": 8, "temperature_unit": "celsius"}))
    daily = data.get("daily")
    forecast = {}
    if isinstance(daily, dict) and isinstance(daily.get("time"), list):
        fields = [daily.get(key) for key in FORECAST_FIELDS]
        for index, raw_day in enumerate(daily["time"]):
            try:
                day = date.fromisoformat(raw_day)
            except (TypeError, ValueError):
                continue
            code, high, low, rain = (field[index] if isinstance(field, list) and index < len(field)
                                     else None for field in fields)
            forecast[day] = (WMO_CONDITIONS.get(code) if type(code) is int else None, high, low, rain)
    return forecast, datetime.now(timezone).date(), "°C"


def forecast_reply(opener, match):
    kind = match["kind"]
    period = match["first"] or match["last"] or "today"
    place = match["before"] or match["after"] or match["place_only"]
    if place:
        location, error = find_place(opener, place)
        if error:
            return error, "unresolved", "weather"
        name = place_name(location)
        forecast, today, unit = place_forecast(opener, location)
    else:
        name = "home"
        forecast, today, unit = home_forecast(opener)
    if not today:
        return f"I couldn't verify the forecast for {name}.", "unavailable", "weather"

    temperature_only = "temperature" in kind
    rain_only = kind == "will it rain"
    reports = []
    available = 0
    days = forecast_dates(today, period)
    for day in days:
        condition, high, low, probability = forecast.get(day, (None, None, None, None))
        temperatures = [f"{label} of {value}" for label, raw in (("high", high), ("low", low))
                        if (value := reading(raw, unit))]
        chance = (f"up to a {probability:g} percent chance of precipitation"
                  if type(probability) in (int, float) and 0 <= probability <= 100 else None)
        label = day.strftime("%A")
        details = []
        if condition and not temperature_only:
            details.append(f"the forecast shows {condition}")
        if temperatures and not rain_only:
            details.append("expect a " + " and a ".join(temperatures))
        if chance and not temperature_only:
            details.append("there's " + chance)
        if details:
            available += 1
            reports.append(f"On {label}, " + ", and ".join(details) + ".")
        else:
            reports.append(f"I couldn't verify {'the forecast temperature' if temperature_only else 'a forecast'} for {label}.")
    outcome = "confirmed" if available == len(days) else "partial" if available else "unavailable"
    location_intro = "For home" if not place else f"For {name}"
    return location_intro + ". " + " ".join(reports), outcome, "weather"


def forecast_question(phrase):
    match = FORECAST.fullmatch(phrase)
    if match and (match["first"] or match["last"] or "forecast" in match["kind"]
                  or match["kind"] == "will it rain"):
        return match
    return None


def question_context(phrase):
    phrase = phrase.replace("’", "'")
    forecast = forecast_question(phrase)
    if forecast:
        kind = ("temperature" if "temperature" in forecast["kind"] else
                "rain" if forecast["kind"] == "will it rain" else "weather")
        return (kind, forecast["before"] or forecast["after"] or forecast["place_only"],
                forecast["first"] or forecast["last"] or "today")
    phrase = re.sub(r"^what time is it in ", "what is the time in ", phrase)
    if match := PLACE_QUESTION.fullmatch(phrase):
        kind = match["kind"].removeprefix("current ").removesuffix(" like")
        return kind, match["place"], None
    if HOME_WEATHER.fullmatch(phrase) or phrase in INSIDE:
        return ("temperature" if "temperature" in phrase else "weather"), None, None
    return None


def follow_up(phrase, context):
    match = FOLLOW_UP.fullmatch(phrase)
    if not match:
        return phrase, None
    if not context:
        return phrase, "What would you like me to check, and for which place?"
    kind, place, period = context
    if match["home"]:
        place = None
    elif match["place"] or match["day_place"]:
        place = match["place"] or match["day_place"]
    if match["day"]:
        if kind == "time":
            return phrase, "Did you want the weather forecast or the local time?"
        period = match["day"]
    location = f" in {place}" if place else ""
    if period:
        request = {"temperature": "what will the temperature be",
                   "rain": "will it rain"}.get(kind, "what's the weather forecast")
        return f"{request} {period}{location}", None
    if kind == "time" and not place:
        return phrase, "Which place should I check the local time for?"
    return f"what's the {kind}{location}", None


def handle(phrase, opener):
    phrase = phrase.replace("’", "'")
    if forecast := forecast_question(phrase):
        return forecast_reply(opener, forecast)
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
    name = place_name(location)
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
