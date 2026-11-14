"""Admin-only, allowlisted native management operations. No credentials returned."""
import aiohttp
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

GET_PATHS = {
    "export": "/api/native/settings-export",
    "recovery": "/api/native/settings-recovery",
    "diagnostics": "/api/native/diagnostics",
}

class DeclanManagementView(HomeAssistantView):
    url = "/api/declan_two/management/{operation}"
    name = "api:declan_two:management"
    requires_auth = True

    async def _relay(self, request, operation, body=None):
        user = request.get("hass_user")
        if user is None or not user.is_admin:
            return web.json_response({"status": "forbidden"}, status=403)
        entries = request.app["hass"].config_entries.async_entries("declan_two")
        if len(entries) != 1:
            return web.json_response({"status": "not_configured"}, status=503)
        entry = entries[0]
        path = "/api/native/spotify-credentials" if body is not None else GET_PATHS[operation]
        try:
            session = async_get_clientsession(request.app["hass"])
            kwargs = dict(headers={"Authorization": f"Bearer {entry.data['token']}"},
                          timeout=aiohttp.ClientTimeout(total=15), allow_redirects=False)
            url = entry.data["url"].rstrip("/") + path
            async with (session.post(url, json=body, **kwargs) if body is not None
                        else session.get(url, **kwargs)) as response:
                if response.status != 200:
                    return web.json_response({"status": "backend_unavailable"}, status=502)
                payload = await response.json(content_type="application/json")
                if not isinstance(payload, dict):
                    raise ValueError("Invalid response")
                if body is not None:
                    return web.json_response({"saved": payload.get("source") == "saved"},
                                             headers={"Cache-Control": "no-store"})
                if operation in {"export", "recovery"}:
                    document = payload.get("document")
                    if not isinstance(document, dict) or document.get("format") != "declan-settings":
                        raise ValueError("Invalid settings document")
                    return web.json_response({"document": document}, headers={"Cache-Control": "no-store"})
                traces = payload.get("traces")
                if not isinstance(traces, list):
                    raise ValueError("Invalid diagnostics")
                return web.json_response({"traces": traces[:30]}, headers={"Cache-Control": "no-store"})
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError):
            return web.json_response({"status": "backend_unavailable"}, status=502)

    async def get(self, request):
        operation = request.match_info.get("operation")
        if operation not in GET_PATHS:
            return web.json_response({"status": "invalid_operation"}, status=404)
        return await self._relay(request, operation)

    async def post(self, request):
        if request.match_info.get("operation") != "spotify":
            return web.json_response({"status": "invalid_operation"}, status=404)
        if request.content_type != "application/json" or request.content_length is None or not 0 < request.content_length <= 2048:
            return web.json_response({"status": "invalid_request"}, status=400)
        try:
            body = await request.json()
        except (ValueError, TypeError):
            return web.json_response({"status": "invalid_json"}, status=400)
        if not isinstance(body, dict) or set(body) != {"client_id", "client_secret", "confirm"} or body.get("confirm") is not True:
            return web.json_response({"status": "invalid_request"}, status=400)
        if not all(isinstance(body[key], str) and 0 < len(body[key]) <= 256 for key in ("client_id", "client_secret")):
            return web.json_response({"status": "invalid_credentials"}, status=400)
        return await self._relay(request, "spotify", body)
