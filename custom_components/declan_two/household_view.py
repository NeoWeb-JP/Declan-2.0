"""Admin-only household settings proxy (FUT-60). Never expose backend tokens to the panel."""
import aiohttp
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

CHOICES = {"guest_tone": frozenset({"home", "polite"})}
SOURCES = frozenset({"saved", "environment", "default"})
# hass.data key holding the last guest tone read from the backend, for the TTS
# catalogue fallback. Missing means "home", the owner's default.
DATA_KEY = "declan_two_household"


def valid_settings(settings):
    return (isinstance(settings, dict) and set(settings) == set(CHOICES)
            and all(settings[key] in choices for key, choices in CHOICES.items()))


def remember(hass, settings):
    hass.data[DATA_KEY] = dict(settings)


def guest_tone(hass):
    stored = getattr(hass, "data", {}).get(DATA_KEY, {})
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
        if request.content_type != "application/json" or request.content_length is None or not 0 < request.content_length <= 1024:
            return web.json_response({"error": "Invalid content"}, status=400)
        try:
            body = await request.json()
        except (ValueError, TypeError):
            return web.json_response({"error": "Invalid JSON"}, status=400)
        if not isinstance(body, dict) or set(body) != {"settings"} or not valid_settings(body["settings"]):
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
                sources = data.get("sources") if isinstance(data, dict) else None
                if (not valid_settings(data.get("settings")) or not isinstance(sources, dict)
                        or set(sources) != set(CHOICES) or not set(sources.values()) <= SOURCES):
                    raise ValueError("Invalid response")
                remember(hass, data["settings"])
                return web.json_response({"settings": data["settings"], "sources": sources},
                                         headers={"Cache-Control": "no-store"})
        except (aiohttp.ClientError, TimeoutError, ValueError, KeyError, TypeError, AttributeError):
            return web.json_response({"error": "Backend unavailable"}, status=502)
