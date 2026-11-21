"""Morning briefing (FUT-29, #834).

"What's my day look like?", "morning briefing", "brief me": a short briefing
of the weather, today's calendar, the car's charge and bin day. It's added to
the Good Morning routine's reply too (Settings -> Household -> Briefing), and
never on the first wake word of the day.

- Reads only the sources switched on in Settings (``house_info.briefing``).
  A source that's missing, empty or not answering is skipped silently.
- Short: at most about 45 words (roughly 15 seconds spoken). Parts are added
  in order (weather, bins, calendar, car) and the rest dropped if it runs long.
- Guest mode: weather and bins only. The calendar and the car stay private.
- Bins are only mentioned when a collection is today or tomorrow.
"""
import os
import re
from datetime import date, datetime, time as day_time, timedelta

from declan.core.execution_results import ExecutionResult, Outcome
from declan.ha import car, ha_reads, house_info

MAX_WORDS = 45
MAX_EVENTS = 3
_ASK = re.compile(r"(?:what(?:'s| is| does) (?:my|our|the) day (?:look(?:ing)? like|got in store|have in store)"
                  r"|what(?:'s| is) (?:on |happening )?(?:for |on )?today|what(?:'s| is) (?:on )?the plan (?:for )?today"
                  r"|(?:give me |read me |do )?(?:the |my |a |our )?(?:morning |daily )?briefing(?: please)?"
                  r"|brief me(?: please)?|what do i need to know (?:about )?today)")
_CONDITIONS = {
    "clear-night": "clear", "cloudy": "cloudy", "exceptional": "unusual weather", "fog": "foggy", "hail": "hail",
    "lightning": "thunderstorms", "lightning-rainy": "thunderstorms and rain", "partlycloudy": "partly cloudy",
    "pouring": "heavy rain", "rainy": "rain", "snowy": "snow", "snowy-rainy": "sleet", "sunny": "sunny",
    "windy": "windy", "windy-variant": "windy and cloudy",
}
_UNKNOWN = frozenset({"unknown", "unavailable", "", "none"})


def match(phrase):
    """("briefing",) | None."""
    if not isinstance(phrase, str):
        return None
    text = " ".join(phrase.casefold().replace("’", "'").split()).strip(" ?.!")
    text = re.sub(r"^(?:declan,? |hey declan,? |howzit declan,? |morning declan,? |good morning declan,? )", "", text)
    text = re.sub(r",? declan$", "", text)
    return ("briefing",) if _ASK.fullmatch(text) else None


def _number(value):
    return round(value) if type(value) in (int, float) else None


def weather(connection, *, timeout=4):
    entity = os.environ.get("DECLAN_WEATHER_ENTITY", "weather.forecast_home").strip()
    if not re.fullmatch(r"weather\.[a-z0-9_]+", entity):
        return None
    data = ha_reads.call(connection, "/api/services/weather/get_forecasts?return_response",
                         {"entity_id": entity, "type": "daily"}, timeout=timeout)
    response = data.get("service_response") if isinstance(data, dict) else None
    forecast = ((response or {}).get(entity) or {}).get("forecast") if isinstance(response, dict) else None
    if not isinstance(forecast, list) or not forecast or not isinstance(forecast[0], dict):
        return None
    today = forecast[0]
    raw_condition = today.get("condition")
    condition = _CONDITIONS.get(raw_condition) if isinstance(raw_condition, str) else None
    high, low, rain = _number(today.get("temperature")), _number(today.get("templow")), _number(
        today.get("precipitation_probability"))
    parts = []
    if condition:
        parts.append(condition)
    if high is not None:
        parts.append(f"a high of {high}" + (f" and a low of {low}" if low is not None else ""))
    if rain is not None and rain >= 20:
        parts.append(f"{rain}% chance of rain")
    return "Today: " + ", ".join(parts) + "." if parts else None


def _when(value):
    """(date, "10:30" or None for all day) from an event's start."""
    if not isinstance(value, str):
        return None, None
    try:
        if len(value) == 10:
            return date.fromisoformat(value), None
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None, None
    moment = moment.astimezone() if moment.tzinfo else moment
    return moment.date(), f"{moment:%H:%M}"


def _events(connection, entities, start, end, *, timeout=4):
    data = ha_reads.call(connection, "/api/services/calendar/get_events?return_response",
                         {"entity_id": entities, "start_date_time": start.isoformat(),
                          "end_date_time": end.isoformat()}, timeout=timeout)
    response = data.get("service_response") if isinstance(data, dict) else None
    events = []
    for entity in entities:
        rows = ((response or {}).get(entity) or {}).get("events") if isinstance(response, dict) else None
        for row in rows if isinstance(rows, list) else ():
            if isinstance(row, dict) and isinstance(row.get("summary"), str) and row["summary"].strip():
                day, clock = _when(row.get("start"))
                events.append((day, clock or "", row["summary"].strip()[:60]))
    return sorted(events, key=lambda event: (event[0] or date.min, event[1]))


def _calendars(connection):
    rows = ha_reads.template(connection, "{{ states.calendar | map(attribute='entity_id') | list | to_json }}")
    return [row for row in rows if isinstance(row, str)] if isinstance(rows, list) else []


def calendar(connection, *, now=None, timeout=4):
    now = now or datetime.now().astimezone()
    chosen = house_info.split(house_info.get("calendars"))
    if not chosen:
        bins = house_info.get("bins")
        chosen = [entity for entity in _calendars(connection) if entity != bins]
    if not chosen:
        return None
    end = datetime.combine(now.date() + timedelta(days=1), day_time.min, tzinfo=now.tzinfo)
    events = [event for event in _events(connection, chosen, now, end, timeout=timeout)
              if event[0] in {None, now.date()}]
    if not events:
        return "Nothing on the calendar."
    named = [f"{summary} at {clock}" if clock else summary for _, clock, summary in events[:MAX_EVENTS]]
    more = len(events) - len(named)
    listed = named[0] if len(named) == 1 else ", ".join(named[:-1]) + " and " + named[-1]
    if more:
        listed = ", ".join(named) + f" and {more} more"
    return f"On the calendar: {listed}."


def bins(connection, *, now=None, timeout=4):
    entity = house_info.get("bins")
    if not entity:
        return None
    now = now or datetime.now().astimezone()
    if entity.startswith("calendar."):
        start = datetime.combine(now.date(), day_time.min, tzinfo=now.tzinfo)
        events = _events(connection, [entity], start, start + timedelta(days=2), timeout=timeout)
        today = [summary for day, _, summary in events if day == now.date()]
        tomorrow = [summary for day, _, summary in events if day == now.date() + timedelta(days=1)]
        if today:
            return f"Bins: {' and '.join(today[:2])} today."
        if tomorrow:
            return f"Bins: {' and '.join(tomorrow[:2])} tomorrow, so out they go tonight."
        return None
    state = ha_reads.call(connection, f"/api/states/{entity}", timeout=timeout)
    if not isinstance(state, dict):
        return None
    value = state.get("state")
    raw_attributes = state.get("attributes")
    attributes: dict = raw_attributes if isinstance(raw_attributes, dict) else {}
    if not isinstance(value, str) or value.casefold() in _UNKNOWN:
        return None
    days = attributes.get("daysTo")
    soon = (type(days) is int and 0 <= days <= 1) or bool(re.search(r"\b(?:today|tomorrow)\b", value, re.IGNORECASE))
    if not soon:
        return None
    name = attributes.get("friendly_name") if isinstance(attributes.get("friendly_name"), str) else "Bins"
    text = value if re.search(r"[a-z]", value, re.IGNORECASE) else f"in {value} days"
    if type(days) is int and not re.search(r"\b(?:today|tomorrow)\b", value, re.IGNORECASE):
        text = "today" if days == 0 else "tomorrow"
    return f"{name}: {text}."


def compose(connection, *, guest=False, now=None, timeout=4):
    """The briefing text, or "" when nothing is configured or answering."""
    try:
        items = house_info.split(house_info.get("briefing"))
    except (OSError, ValueError, KeyError):
        items = list(house_info.BRIEFING_ITEMS)
    order = [item for item in ("weather", "bins", "calendar", "car") if item in items]
    if guest:
        order = [item for item in order if item in {"weather", "bins"}]
    readers = {"weather": lambda: weather(connection, timeout=timeout),
               "bins": lambda: bins(connection, now=now, timeout=timeout),
               "calendar": lambda: calendar(connection, now=now, timeout=timeout),
               "car": lambda: car.summary(connection)}
    parts, words = [], 0
    for item in order:
        try:
            part = readers[item]()
        except (OSError, ValueError, TypeError, KeyError, AttributeError, TimeoutError):
            part = None  # a missing source is skipped silently
        if not part:
            continue
        count = len(part.split())
        if words + count > MAX_WORDS:
            break
        parts.append(part)
        words += count
    return " ".join(parts)


def result(request, connection, *, guest):
    if request is None:
        return None
    if connection is None:
        return ExecutionResult("The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED)
    text = compose(connection, guest=guest)
    if not text:
        return ExecutionResult("I've got nothing for you. Switch on the briefing's weather, calendar, car or bins in "
                               "Settings, Household, Briefing.", Outcome.NOT_CONFIGURED)
    return ExecutionResult(text, Outcome.CHAT_ANSWER)


def for_good_morning(connection, *, guest):
    """The briefing to add after Good Morning, or "" (switched off, or nothing to say)."""
    try:
        if not house_info.get("briefing_in_good_morning"):
            return ""
    except (OSError, ValueError, KeyError):
        return ""
    try:
        return compose(connection, guest=guest, timeout=3)
    except (OSError, ValueError, TypeError):
        return ""
