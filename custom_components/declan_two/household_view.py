"""Admin-only household settings proxy (personality sliders, FUT-60, FUT-61, FUT-42, FUT-44, FUT-46, FUT-31, FUT-29, FUT-32). Never expose backend tokens to the panel."""
import re

import aiohttp
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

CHOICES = {"guest_tone": frozenset({"home", "polite"})}
KEYS = frozenset({"guest_tone", "shelve_days", "fresh_lines", "christmas", "wifi_name", "wifi_password",
                  "shopping_list"})
_TODO_ENTITY = re.compile(r"(?:todo\.[a-z0-9_]{1,100})?")
SOURCES = frozenset({"saved", "environment", "default"})
# hass.data key holding the last guest tone read from the backend, for the TTS
# catalogue fallback. Missing means "home", the owner's default.
DATA_KEY = "declan_two_household"


def valid_settings(settings, *, complete=True):
    """Every key in a backend reply; a save may leave out the FUT-61 keys.

    An older backend has no shopping_list yet, so a reply without it is still valid.
    """
    if not isinstance(settings, dict) or not set(settings) <= KEYS or "guest_tone" not in settings:
        return False
    if complete and set(settings) | {"shopping_list"} != KEYS:
        return False
    return (settings["guest_tone"] in CHOICES["guest_tone"]
            and ("shelve_days" not in settings or (type(settings["shelve_days"]) is int and 0 <= settings["shelve_days"] <= 30))
            and ("fresh_lines" not in settings or type(settings["fresh_lines"]) is bool)
            and ("christmas" not in settings or settings["christmas"] in {"auto", "on", "off"})
            and all(name not in settings or (isinstance(settings[name], str) and len(settings[name]) <= 63
                                             and all(" " <= ch <= "~" for ch in settings[name]))
                    for name in ("wifi_name", "wifi_password"))
            and ("shopping_list" not in settings or (isinstance(settings["shopping_list"], str)
                                                     and bool(_TODO_ENTITY.fullmatch(settings["shopping_list"])))))


def valid_delete(body):
    target = body.get("delete_line") if isinstance(body, dict) and set(body) == {"delete_line"} else None
    return (isinstance(target, dict) and set(target) == {"key", "line"}
            and all(isinstance(target[name], str) and 0 < len(target[name]) <= 400 for name in ("key", "line")))


def valid_forget(body):
    return (isinstance(body, dict) and set(body) == {"forget_item"} and isinstance(body["forget_item"], str)
            and 0 < len(body["forget_item"]) <= 80)


PERSONALITY_TRAITS = frozenset({"sass", "rudeness", "humour", "slang", "chattiness", "swearing", "insults"})
PERSONALITY_AUDIENCES = frozenset({"household", "guests"})


def _valid_dials(value):
    return (isinstance(value, dict) and set(value) == PERSONALITY_AUDIENCES
            and all(isinstance(value[audience], dict) and set(value[audience]) == PERSONALITY_TRAITS
                    and all(type(level) is int and 1 <= level <= 10 for level in value[audience].values())
                    for audience in PERSONALITY_AUDIENCES))


def valid_personality_change(body):
    """{"save_personality": {"household": {trait: 1-10}, "guests": {trait: 1-10}}}."""
    return isinstance(body, dict) and set(body) == {"save_personality"} and _valid_dials(body["save_personality"])


def valid_personality(value):
    """Personality listing from the backend, or None when it couldn't be read."""
    if value is None:
        return True
    return (isinstance(value, dict) and _valid_dials(value.get("settings"))
            and isinstance(value.get("sources"), dict) and set(value["sources"]) == PERSONALITY_AUDIENCES
            and set(value["sources"].values()) <= {"saved", "default"}
            and isinstance(value.get("traits"), list) and set(value["traits"]) == PERSONALITY_TRAITS
            and isinstance(value.get("labels"), dict) and set(value["labels"]) == PERSONALITY_TRAITS
            and all(isinstance(label, str) and len(label) <= 40 for label in value["labels"].values())
            and ("forgotten" not in value or value["forgotten"] is None or type(value["forgotten"]) is int))


USUAL_WINDOWS = frozenset({"morning", "afternoon", "evening", "night", "any"})


def _usual_room(value):
    return isinstance(value, str) and 0 < len(value) <= 40


def valid_usual_change(body):
    """FUT-44: {"save_usual": {room, window, steps}} or {"forget_usual": {room, window}}."""
    if not isinstance(body, dict) or len(body) != 1 or not set(body) <= {"save_usual", "forget_usual"}:
        return False
    target = next(iter(body.values()))
    if not isinstance(target, dict) or not _usual_room(target.get("room")) or target.get("window") not in USUAL_WINDOWS:
        return False
    if "forget_usual" in body:
        return set(target) == {"room", "window"}
    steps = target.get("steps")
    return (set(target) == {"room", "window", "steps"} and isinstance(steps, list) and 0 < len(steps) <= 5
            and all(isinstance(step, str) and 0 < len(step) <= 80 for step in steps))


def valid_usuals(value):
    if value is None:
        return True
    return (isinstance(value, list) and len(value) <= 100
            and all(isinstance(row, dict) and _usual_room(row.get("room")) and row.get("window") in USUAL_WINDOWS
                    and isinstance(row.get("steps"), list) and all(isinstance(step, str) for step in row["steps"])
                    and isinstance(row.get("saved_at"), (int, float)) for row in value))


def valid_theme_change(body):
    """FUT-46: {"save_theme": {person, media_id, enabled}}, {"theme_satellite": str} or {"try_theme": person}."""
    if not isinstance(body, dict) or len(body) != 1:
        return False
    if "theme_satellite" in body:
        value = body["theme_satellite"]
        return isinstance(value, str) and (value == "" or bool(re.fullmatch(r"assist_satellite\.[a-z0-9_]{1,80}", value)))
    if "try_theme" in body:
        return isinstance(body["try_theme"], str) and bool(re.fullmatch(r"person\.[a-z0-9_]{1,80}", body["try_theme"]))
    target = body.get("save_theme")
    return (isinstance(target, dict) and set(target) == {"person", "media_id", "enabled"}
            and isinstance(target["person"], str) and bool(re.fullmatch(r"person\.[a-z0-9_]{1,80}", target["person"]))
            and isinstance(target["media_id"], str) and len(target["media_id"]) <= 300
            and type(target["enabled"]) is bool)


def valid_themes(value):
    if value is None:
        return True
    return (isinstance(value, dict) and isinstance(value.get("satellite"), str)
            and isinstance(value.get("people"), list) and len(value["people"]) <= 50
            and all(isinstance(row, dict) and isinstance(row.get("person"), str) and isinstance(row.get("name"), str)
                    and isinstance(row.get("media_id"), str) and type(row.get("enabled")) is bool
                    and type(row.get("home")) is bool for row in value["people"]))


HOUSE_INFO_KEYS = frozenset({"car_name", "car_battery", "car_in_sunrise", "briefing", "calendars", "bins",
                             "briefing_in_good_morning"})
BRIEFING_ITEMS = frozenset({"weather", "calendar", "car", "bins"})


def _items(value):
    return [item.strip() for item in value.split(",") if item.strip()]


def _valid_house_value(key, value):
    if key == "car_name":
        return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 '\-]{0,29}", value))
    if key == "car_battery":
        return isinstance(value, str) and (value == "" or bool(re.fullmatch(r"sensor\.[a-z0-9_]{1,100}", value)))
    if key in {"car_in_sunrise", "briefing_in_good_morning"}:
        return type(value) is bool
    if key == "briefing":
        return isinstance(value, str) and len(value) <= 60 and set(_items(value)) <= BRIEFING_ITEMS
    if key == "calendars":
        return isinstance(value, str) and len(value) <= 600 and all(
            re.fullmatch(r"calendar\.[a-z0-9_]{1,100}", item) for item in _items(value))
    if key == "bins":
        return isinstance(value, str) and (value == "" or bool(re.fullmatch(r"(?:calendar|sensor)\.[a-z0-9_]{1,100}", value)))
    return False


def valid_house_info_change(body):
    """#834 P2: {"save_house_info": {...}} with any of HOUSE_INFO_KEYS (car FUT-31, briefing FUT-29)."""
    target = body.get("save_house_info") if isinstance(body, dict) and set(body) == {"save_house_info"} else None
    return (isinstance(target, dict) and bool(target) and set(target) <= HOUSE_INFO_KEYS
            and all(_valid_house_value(key, value) for key, value in target.items()))


def valid_house_info(value):
    if value is None:
        return True
    settings = value.get("settings") if isinstance(value, dict) else None
    sources = value.get("sources") if isinstance(value, dict) else None
    return (isinstance(settings, dict) and set(settings) == HOUSE_INFO_KEYS
            and all(_valid_house_value(key, item) for key, item in settings.items())
            and isinstance(sources, dict) and set(sources) == HOUSE_INFO_KEYS and set(sources.values()) <= SOURCES)


SATELLITE_CAPABILITIES = frozenset({"audio", "announce", "reply", "screen"})


def valid_satellite_change(body):
    """FUT-32: {"save_satellite": {entity_id, audio?, announce?, reply?, screen?}}; null clears an override."""
    target = body.get("save_satellite") if isinstance(body, dict) and set(body) == {"save_satellite"} else None
    return (isinstance(target, dict) and isinstance(target.get("entity_id"), str)
            and bool(re.fullmatch(r"assist_satellite\.[a-z0-9_]{1,80}", target["entity_id"]))
            and set(target) - {"entity_id"} <= SATELLITE_CAPABILITIES
            and all(value is None or type(value) is bool for key, value in target.items() if key != "entity_id"))


def valid_satellites(value):
    if value is None:
        return True

    def flags(item, partial):
        return (isinstance(item, dict) and (set(item) <= SATELLITE_CAPABILITIES if partial
                                            else set(item) == SATELLITE_CAPABILITIES)
                and all(type(flag) is bool for flag in item.values()))
    return (isinstance(value, list) and len(value) <= 40
            and all(isinstance(row, dict) and isinstance(row.get("entity_id"), str) and isinstance(row.get("area"), str)
                    and isinstance(row.get("name"), str) and isinstance(row.get("state"), str)
                    and flags(row.get("detected"), False) and flags(row.get("capabilities"), False)
                    and flags(row.get("overrides"), True) for row in value))


def valid_whereabouts(value):
    if value is None:
        return True
    return (isinstance(value, list) and len(value) <= 500
            and all(isinstance(row, dict) and isinstance(row.get("item"), str) and isinstance(row.get("place"), str)
                    and isinstance(row.get("saved_at"), (int, float)) for row in value))


def valid_pantry(value):
    """Pantry stock listing (FUT-76), or None when the backend couldn't read it."""
    if value is None:
        return True
    return (isinstance(value, list) and len(value) <= 300
            and all(isinstance(row, dict) and isinstance(row.get("item"), str) and isinstance(row.get("unit"), str)
                    and type(row.get("count")) is int and type(row.get("minimum")) is int
                    and isinstance(row.get("updated_at"), (int, float)) for row in value))


def valid_generated(value):
    """Generated lines listing, or None when the backend couldn't read it."""
    if value is None:
        return True
    return (isinstance(value, dict) and isinstance(value.get("lines"), list) and len(value["lines"]) <= 5000
            and all(isinstance(row, dict) and isinstance(row.get("key"), str) and isinstance(row.get("line"), str)
                    and isinstance(row.get("created"), (int, float)) for row in value["lines"])
            and all(type(value.get(name)) is int for name in ("spent_micro_usd", "budget_micro_usd")))


def remember(hass, settings):
    hass.data[DATA_KEY] = dict(settings)


def guest_tone(hass):
    stored = getattr(hass, "data", {}).get(DATA_KEY, {})  # guest_tone only
    tone = stored.get("guest_tone") if isinstance(stored, dict) else None
    return tone if tone in CHOICES["guest_tone"] else "home"


async def refresh(hass, entry):
    """Best effort at startup: read the backend's household settings into hass.data."""
    try:
        session = async_get_clientsession(hass)
        async with session.get(entry.data["url"] + "/api/settings/household",
                               headers={"Authorization": f"Bearer {entry.data['token']}"},
                               timeout=aiohttp.ClientTimeout(total=10), allow_redirects=False) as response:
            if response.status != 200:
                return
            data = await response.json(content_type="application/json")
    except (aiohttp.ClientError, TimeoutError, ValueError, KeyError, TypeError, AttributeError):
        return
    if isinstance(data, dict) and valid_settings(data.get("settings")):
        remember(hass, data["settings"])


class DeclanHouseholdView(HomeAssistantView):
    url = "/api/declan_two/household"
    name = "api:declan_two:household"
    requires_auth = True

    async def get(self, request):
        return await self._relay(request)

    async def post(self, request):
        if request.content_type != "application/json" or request.content_length is None or not 0 < request.content_length <= 2048:
            return web.json_response({"error": "Invalid content"}, status=400)
        try:
            body = await request.json()
        except (ValueError, TypeError):
            return web.json_response({"error": "Invalid JSON"}, status=400)
        if (valid_delete(body) or valid_forget(body) or valid_usual_change(body) or valid_theme_change(body)
                or valid_house_info_change(body) or valid_satellite_change(body)
                or valid_personality_change(body)):
            return await self._relay(request, body)
        if not isinstance(body, dict) or set(body) != {"settings"} or not valid_settings(body["settings"], complete=False):
            return web.json_response({"error": "Invalid settings"}, status=400)
        return await self._relay(request, body)

    async def _relay(self, request, body=None):
        user = request.get("hass_user")
        if user is None or not user.is_admin:
            return web.json_response({"error": "Admin required"}, status=403)
        hass = request.app["hass"]
        entries = hass.config_entries.async_entries("declan_two")
        if len(entries) != 1:
            return web.json_response({"error": "Not configured"}, status=503)
        entry = entries[0]
        try:
            session = async_get_clientsession(hass)
            url = entry.data["url"] + "/api/settings/household"
            kwargs = {"headers": {"Authorization": f"Bearer {entry.data['token']}"},
                      "timeout": aiohttp.ClientTimeout(total=10), "allow_redirects": False}
            async with (session.get(url, **kwargs) if body is None else session.post(url, json=body, **kwargs)) as response:
                if response.status != 200:
                    return web.json_response({"error": "Invalid settings" if response.status == 400 else "Backend unavailable"},
                                             status=400 if response.status == 400 else 502)
                data = await response.json(content_type="application/json")
                if body is not None and "forget_item" in body:
                    if not isinstance(data, dict) or type(data.get("forgotten")) is not bool:
                        raise ValueError("Invalid response")
                    return web.json_response({"forgotten": data["forgotten"]}, headers={"Cache-Control": "no-store"})
                if body is not None and "save_usual" in body:
                    steps = data.get("steps") if isinstance(data, dict) else None
                    if data.get("saved") is not True or not isinstance(steps, list) or not all(
                            isinstance(step, str) for step in steps):
                        raise ValueError("Invalid response")
                    return web.json_response({"saved": True, "steps": steps}, headers={"Cache-Control": "no-store"})
                if body is not None and "save_satellite" in body:
                    overrides = data.get("overrides") if isinstance(data, dict) else None
                    if data.get("saved") is not True or not isinstance(overrides, dict) or not set(
                            overrides) <= SATELLITE_CAPABILITIES:
                        raise ValueError("Invalid response")
                    return web.json_response({"saved": True, "overrides": overrides},
                                             headers={"Cache-Control": "no-store"})
                if body is not None and "save_house_info" in body:
                    if not isinstance(data, dict) or data.get("saved") is not True or not valid_house_info(
                            data.get("house_info")) or data.get("house_info") is None:
                        raise ValueError("Invalid response")
                    return web.json_response({"saved": True, "house_info": data["house_info"]},
                                             headers={"Cache-Control": "no-store"})
                if body is not None and set(body) & {"save_theme", "theme_satellite", "try_theme"}:
                    if not isinstance(data, dict) or not (data.get("saved") is True or data.get("played") is True):
                        raise ValueError("Invalid response")
                    reply = {key: data[key] for key in ("saved", "played", "satellite", "theme") if key in data}
                    return web.json_response(reply, headers={"Cache-Control": "no-store"})
                if body is not None and "save_personality" in body:
                    personality = data.get("personality") if isinstance(data, dict) else None
                    if data.get("saved") is not True or personality is None or not valid_personality(personality):
                        raise ValueError("Invalid response")
                    reply = {key: personality[key] for key in ("settings", "sources", "traits", "labels", "forgotten")
                             if key in personality}
                    return web.json_response({"saved": True, "personality": reply},
                                             headers={"Cache-Control": "no-store"})
                if body is not None and "forget_usual" in body:
                    if not isinstance(data, dict) or type(data.get("forgotten")) is not bool:
                        raise ValueError("Invalid response")
                    return web.json_response({"forgotten": data["forgotten"]}, headers={"Cache-Control": "no-store"})
                if body is not None and "delete_line" in body:
                    if not isinstance(data, dict) or type(data.get("deleted")) is not bool:
                        raise ValueError("Invalid response")
                    return web.json_response({"deleted": data["deleted"]}, headers={"Cache-Control": "no-store"})
                sources = data.get("sources") if isinstance(data, dict) else None
                if (not valid_settings(data.get("settings")) or not isinstance(sources, dict)
                        or set(sources) | {"shopping_list"} != KEYS or not set(sources.values()) <= SOURCES
                        or not valid_generated(data.get("generated"))
                        or not valid_whereabouts(data.get("whereabouts"))
                        or not valid_pantry(data.get("pantry"))
                        or not valid_usuals(data.get("usuals"))
                        or not valid_themes(data.get("themes"))
                        or not valid_house_info(data.get("house_info"))
                        or not valid_satellites(data.get("satellites"))
                        or not valid_personality(data.get("personality"))):
                    raise ValueError("Invalid response")
                remember(hass, data["settings"])
                payload = {"settings": data["settings"], "sources": sources}
                for extra in ("generated", "whereabouts", "pantry", "usuals", "themes", "house_info", "satellites"):
                    if extra in data:
                        payload[extra] = data[extra]
                if isinstance(data.get("personality"), dict):
                    payload["personality"] = {key: data["personality"][key] for key in
                                              ("settings", "sources", "traits", "labels")}
                return web.json_response(payload, headers={"Cache-Control": "no-store"})
        except (aiohttp.ClientError, TimeoutError, ValueError, KeyError, TypeError, AttributeError):
            return web.json_response({"error": "Backend unavailable"}, status=502)
