"""Read-only secret-free native settings status."""
import aiohttp
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

class DeclanSettingsStatusView(HomeAssistantView):
    url = "/api/declan_two/settings-status"
    name = "api:declan_two:settings-status"
    requires_auth = True

    async def get(self, request):
        user = request.get("hass_user")
        if user is None or not user.is_admin:
            return web.json_response({"status": "forbidden"}, status=403)
        entries = request.app["hass"].config_entries.async_entries("declan_two")
        if len(entries) != 1:
            return web.json_response({"status": "not_configured"}, status=503)
        entry = entries[0]
        try:
            async with async_get_clientsession(request.app["hass"]).get(
                entry.data["url"].rstrip("/") + "/api/native/settings-status",
                headers={"Authorization": f"Bearer {entry.data['token']}"},
                timeout=aiohttp.ClientTimeout(total=10),
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    return web.json_response({"status": "backend_unavailable"}, status=502)
                payload = await response.json(content_type="application/json")
                if not isinstance(payload, dict):
                    raise ValueError("Invalid response")
                return web.json_response({
                    "spotify_configured": payload.get("spotify_configured") is True,
                    "spotify_source": payload.get("spotify_source") if payload.get("spotify_source") in {"saved", "environment", "unconfigured"} else "unknown",
                }, headers={"Cache-Control": "no-store"})
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError):
            return web.json_response({"status": "backend_unavailable"}, status=502)
