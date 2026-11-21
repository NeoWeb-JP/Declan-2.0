"""Admin-only music behaviour settings proxy. Never expose backend tokens to the panel."""
import aiohttp
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

KEYS = frozenset({"reply_first", "music_assistant_search"})
SOURCES = frozenset({"saved", "environment", "default"})


def valid_settings(settings):
    return isinstance(settings, dict) and set(settings) == KEYS and all(type(v) is bool for v in settings.values())


def valid_percent(value):
    return type(value) is int and 0 <= value <= 100


def valid_start_volume(value):
    """Backend reply: {"percent": 0-100, "source": ...}. Older backends send none."""
    return (isinstance(value, dict) and set(value) == {"percent", "source"}
            and valid_percent(value["percent"]) and value["source"] in SOURCES)


class DeclanMusicSettingsView(HomeAssistantView):
    url = "/api/declan_two/music-settings"
    name = "api:declan_two:music-settings"
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
        if (isinstance(body, dict) and set(body) == {"unblock_artist"} and isinstance(body["unblock_artist"], str)
                and 0 < len(body["unblock_artist"]) <= 200):
            return await self._relay(request, body)
        if (not isinstance(body, dict) or "settings" not in body or not set(body) <= {"settings", "start_volume"}
                or not valid_settings(body["settings"])
                or ("start_volume" in body and not valid_percent(body["start_volume"]))):
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
            url = entry.data["url"] + "/api/settings/music"
            kwargs = {"headers": {"Authorization": f"Bearer {entry.data['token']}"},
                      "timeout": aiohttp.ClientTimeout(total=10), "allow_redirects": False}
            async with (session.get(url, **kwargs) if body is None else session.post(url, json=body, **kwargs)) as response:
                if response.status != 200:
                    return web.json_response({"error": "Invalid settings" if response.status == 400 else "Backend unavailable"},
                                             status=400 if response.status == 400 else 502)
                data = await response.json(content_type="application/json")
                if body is not None and "unblock_artist" in body:
                    if not isinstance(data, dict) or type(data.get("unblocked")) is not bool:
                        raise ValueError("Invalid response")
                    return web.json_response({"unblocked": data["unblocked"]}, headers={"Cache-Control": "no-store"})
                sources = data.get("sources") if isinstance(data, dict) else None
                if (not valid_settings(data.get("settings")) or not isinstance(sources, dict)
                        or set(sources) != KEYS or not set(sources.values()) <= SOURCES):
                    raise ValueError("Invalid response")
                payload = {"settings": data["settings"], "sources": sources}
                if valid_start_volume(data.get("start_volume")):
                    payload["start_volume"] = data["start_volume"]
                artists = data.get("blocked_artists")
                if isinstance(artists, list) and len(artists) <= 1000 and all(isinstance(name, str) for name in artists):
                    payload["blocked_artists"] = artists
                return web.json_response(payload, headers={"Cache-Control": "no-store"})
        except (aiohttp.ClientError, TimeoutError, ValueError, KeyError, TypeError, AttributeError):
            return web.json_response({"error": "Backend unavailable"}, status=502)
