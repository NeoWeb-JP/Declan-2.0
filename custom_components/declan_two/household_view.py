"""Admin-only household settings proxy (FUT-60, FUT-61, FUT-42, FUT-44). Never expose backend tokens to the panel."""
import aiohttp
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

CHOICES = {"guest_tone": frozenset({"home", "polite"})}
KEYS = frozenset({"guest_tone", "shelve_days", "fresh_lines", "christmas", "wifi_name", "wifi_password"})
SOURCES = frozenset({"saved", "environment", "default"})
# hass.data key holding the last guest tone read from the backend, for the TTS
# catalogue fallback. Missing means "home", the owner's default.
DATA_KEY = "declan_two_household"


def valid_settings(settings, *, complete=True):
    """Every key in a backend reply; a save may leave out the FUT-61 keys."""
    if not isinstance(settings, dict) or not set(settings) <= KEYS or "guest_tone" not in settings:
        return False
    if complete and set(settings) != KEYS:
        return False
    return (settings["guest_tone"] in CHOICES["guest_tone"]
            and ("shelve_days" not in settings or (type(settings["shelve_days"]) is int and 0 <= settings["shelve_days"] <= 30))
            and ("fresh_lines" not in settings or type(settings["fresh_lines"]) is bool)
            and ("christmas" not in settings or settings["christmas"] in {"auto", "on", "off"})
            and all(name not in settings or (isinstance(settings[name], str) and len(settings[name]) <= 63
                                             and all(" " <= ch <= "~" for ch in settings[name]))
                    for name in ("wifi_name", "wifi_password")))


def valid_delete(body):
    target = body.get("delete_line") if isinstance(body, dict) and set(body) == {"delete_line"} else None
    return (isinstance(target, dict) and set(target) == {"key", "line"}
            and all(isinstance(target[name], str) and 0 < len(target[name]) <= 400 for name in ("key", "line")))


def valid_forget(body):
    return (isinstance(body, dict) and set(body) == {"forget_item"} and isinstance(body["forget_item"], str)
            and 0 < len(body["forget_item"]) <= 80)


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


def valid_whereabouts(value):
    if value is None:
        return True
    return (isinstance(value, list) and len(value) <= 500
            and all(isinstance(row, dict) and isinstance(row.get("item"), str) and isinstance(row.get("place"), str)
                    and isinstance(row.get("saved_at"), (int, float)) for row in value))


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
        if valid_delete(body) or valid_forget(body) or valid_usual_change(body):
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
                        or set(sources) != KEYS or not set(sources.values()) <= SOURCES
                        or not valid_generated(data.get("generated"))
                        or not valid_whereabouts(data.get("whereabouts"))
                        or not valid_usuals(data.get("usuals"))):
                    raise ValueError("Invalid response")
                remember(hass, data["settings"])
                payload = {"settings": data["settings"], "sources": sources}
                for extra in ("generated", "whereabouts", "usuals"):
                    if extra in data:
                        payload[extra] = data[extra]
                return web.json_response(payload, headers={"Cache-Control": "no-store"})
        except (aiohttp.ClientError, TimeoutError, ValueError, KeyError, TypeError, AttributeError):
            return web.json_response({"error": "Backend unavailable"}, status=502)
