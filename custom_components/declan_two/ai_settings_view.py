"""Admin-only AI settings proxy. Never expose backend tokens to the panel."""
import aiohttp
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession


class DeclanAISettingsView(HomeAssistantView):
    url = "/api/declan_two/ai-settings"
    name = "api:declan_two:ai-settings"
    requires_auth = True

    async def get(self, request):
        return await self._relay(request)

    async def post(self, request):
        if request.content_type != "application/json" or request.content_length is None or not 0 < request.content_length <= 4096:
            return web.json_response({"error": "Invalid content"}, status=400)
        try:
            body = await request.json()
        except (ValueError, TypeError):
            return web.json_response({"error": "Invalid JSON"}, status=400)
        if not isinstance(body, dict) or set(body) not in ({"settings"}, {"api_key"}):
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
            url = entry.data["url"] + "/api/settings/ai"
            kwargs = {"headers": {"Authorization": f"Bearer {entry.data['token']}"},
                      "timeout": aiohttp.ClientTimeout(total=10), "allow_redirects": False}
            async with (session.get(url, **kwargs) if body is None else session.post(url, json=body, **kwargs)) as response:
                if response.status != 200:
                    return web.json_response({"error": "Invalid settings" if response.status == 400 else "Backend unavailable"},
                                             status=400 if response.status == 400 else 502)
                data = await response.json(content_type="application/json")
                if not isinstance(data, dict) or not (isinstance(data.get("settings"), dict) or data.get("key_configured") is True):
                    raise ValueError("Invalid response")
                return web.json_response({key: data[key] for key in ("settings", "key_configured") if key in data}, headers={"Cache-Control": "no-store"})
        except (aiohttp.ClientError, TimeoutError, ValueError, KeyError, TypeError):
            return web.json_response({"error": "Backend unavailable"}, status=502)
