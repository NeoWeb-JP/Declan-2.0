"""Washing weather (FUT-47, #834).

"Is it a good day to hang the washing?", "can I put the washing out?",
"will the washing dry tomorrow?". A verdict from today's (or tomorrow's)
forecast on ``DECLAN_WEATHER_ENTITY``: chance of rain, rain or snow in the
condition, wind and temperature.

- 50% or more chance of rain, or a rainy, stormy or snowy forecast: no.
- 30 to 49%: risky.
- Otherwise yes, with a note when it's windy (extra pegs) or cold (slow).
- Asked late in the day about today: says there isn't much drying time left.
- No forecast, or Home Assistant not answering: says so; never guesses.
"""
import os
import re
from datetime import datetime

from declan.core.execution_results import ExecutionResult, Outcome
from declan.ha import ha_reads

_WASHING = r"(?:the |my |our |some )?(?:washing|laundry|clothes|sheets|towels)"
_DAY = r"(?: (today|tomorrow))?"
_ASK = re.compile(
    rf"(?:is it|is today|is tomorrow|will (?:it|tomorrow) be) (?:a )?good (?:day|weather) (?:to|for) "
    rf"(?:hang(?:ing)?|dry(?:ing)?|put(?:ting)?) (?:out )?{_WASHING}(?: out)?{_DAY}"
    rf"|(?:can|should|shall) (?:i|we) (?:hang|put|peg) (?:out )?{_WASHING}(?: out)?{_DAY}"
    rf"|will {_WASHING} dry(?: outside)?{_DAY}|is it (?:a )?(?:good )?washing (?:day|weather){_DAY}"
    rf"|(?:is it|is today|is tomorrow) (?:a )?(?:good )?drying day{_DAY}"
)
_WET = frozenset({"rainy", "pouring", "lightning", "lightning-rainy", "snowy", "snowy-rainy", "hail", "exceptional"})
_WIND_LIMIT = {"km/h": 35, "mph": 22, "m/s": 10, "kn": 19, "ft/s": 32}
_UNKNOWN = frozenset({"unknown", "unavailable"})


def match(phrase):
    """("washing", "today" | "tomorrow") | None."""
    if not isinstance(phrase, str):
        return None
    text = " ".join(phrase.casefold().replace("’", "'").split()).strip(" ?.!")
    text = re.sub(r"^(?:declan,? |hey declan,? |howzit declan,? )", "", text)
    text = re.sub(r",? declan$", "", text)
    found = _ASK.fullmatch(text)
    if not found:
        return None
    day = next((value for value in found.groups() if value in {"today", "tomorrow"}), None)
    if day is None and "tomorrow" in text.split()[:3]:
        day = "tomorrow"
    return ("washing", day or "today")


def _number(value):
    return value if type(value) in (int, float) else None


def verdict(forecast, *, day="today", wind_unit="km/h", hour=None):
    """The spoken answer for one day's forecast dict."""
    when = "today" if day == "today" else "tomorrow"
    rain = _number(forecast.get("precipitation_probability"))
    condition = forecast.get("condition") if isinstance(forecast.get("condition"), str) else ""
    wind = _number(forecast.get("wind_speed"))
    high = _number(forecast.get("temperature"))
    if condition in _WET or (rain is not None and rain >= 50):
        reason = f"{round(rain)}% chance of rain" if rain is not None and rain >= 50 else {
            "snowy": "snow", "snowy-rainy": "sleet", "hail": "hail", "lightning": "thunderstorms",
            "lightning-rainy": "thunderstorms"}.get(condition, "rain")
        return f"No. {reason[:1].upper() + reason[1:]} {when}. Tumble dryer or the airer, boet."
    if rain is not None and rain >= 30:
        return (f"Risky. {round(rain)}% chance of rain {when}. Peg it out if you're feeling lucky, "
                "and keep an eye on the sky.")
    notes = []
    limit = _WIND_LIMIT.get(wind_unit)
    if wind is not None and limit is not None and wind >= limit:
        notes.append("It's windy, so use extra pegs")
    if high is not None and high < 6:
        notes.append("It's cold, so it'll take all day")
    if day == "today" and hour is not None and hour >= 15:
        notes.append("There's not much drying time left today")
    if rain is None and not condition:
        return None
    reply = f"Yes, {when} looks dry."
    return " ".join([reply] + [note + "." for note in notes])


def _entity():
    entity = os.environ.get("DECLAN_WEATHER_ENTITY", "weather.forecast_home").strip()
    return entity if re.fullmatch(r"weather\.[a-z0-9_]+", entity) else None


def result(request, connection, *, now=None):
    if request is None:
        return None
    if connection is None:
        return ExecutionResult("The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED)
    entity = _entity()
    if entity is None:
        return ExecutionResult("I haven't got a weather forecast set up.", Outcome.NOT_CONFIGURED)
    day = request[1]
    now = now or datetime.now()
    try:
        data = ha_reads.call(connection, "/api/services/weather/get_forecasts?return_response",
                             {"entity_id": entity, "type": "daily"}, timeout=6)
        state = ha_reads.call(connection, f"/api/states/{entity}", timeout=4)
    except (OSError, ValueError, TypeError):
        return ExecutionResult("I couldn't get the forecast from Home Assistant.", Outcome.UNAVAILABLE)
    response = data.get("service_response") if isinstance(data, dict) else None
    forecast = ((response or {}).get(entity) or {}).get("forecast") if isinstance(response, dict) else None
    index = 0 if day == "today" else 1
    if (not isinstance(forecast, list) or len(forecast) <= index or not isinstance(forecast[index], dict)
            or (isinstance(state, dict) and state.get("state") in _UNKNOWN)):
        return ExecutionResult(f"I haven't got a forecast for {day}.", Outcome.UNAVAILABLE)
    raw = state.get("attributes") if isinstance(state, dict) else None
    attributes: dict = raw if isinstance(raw, dict) else {}
    unit = attributes.get("wind_speed_unit") if isinstance(attributes.get("wind_speed_unit"), str) else "km/h"
    reply = verdict(forecast[index], day=day, wind_unit=unit, hour=now.hour)
    if reply is None:
        return ExecutionResult(f"The forecast for {day} doesn't say enough to tell.", Outcome.UNAVAILABLE)
    return ExecutionResult(reply, Outcome.CHAT_ANSWER)
