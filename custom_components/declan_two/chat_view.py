"""Admin-only Home Assistant authenticated chat relay."""
import logging

import aiohttp
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)


class DeclanChatView(HomeAssistantView):
    url = "/api/declan_two/chat"
    name = "api:declan_two:chat"
    requires_auth = True

    async def post(self, request):
        user = request.get("hass_user")
        if user is None or not user.is_admin:
            return web.json_response({"status": "forbidden"}, status=403)
        if request.content_length is None or not 0 < request.content_length <= 4096:
            return web.json_response({"status": "invalid_size"}, status=413)
        if request.content_type != "application/json":
            return web.json_response({"status": "invalid_content_type"}, status=415)
        try:
            payload = await request.json()
        except (ValueError, TypeError):
            return web.json_response({"status": "invalid_json"}, status=400)
        if not isinstance(payload, dict) or set(payload) - {"message", "session_id"} or "message" not in payload:
            return web.json_response({"status": "invalid_message"}, status=400)
        message = payload["message"]
        if not isinstance(message, str) or not 0 < len(message.strip()) <= 1000:
            return web.json_response({"status": "invalid_message"}, status=400)
        session_id = payload.get("session_id")
        if session_id is not None and (not isinstance(session_id, str) or len(session_id) > 64):
            return web.json_response({"status": "invalid_session"}, status=400)
        hass = request.app["hass"]
        entries = hass.config_entries.async_entries("declan_two")
        if len(entries) != 1:
            return web.json_response({"status": "not_configured"}, status=503)
        entry = entries[0]
        try:
            async with async_get_clientsession(hass).post(
                entry.data["url"] + "/api/chat",
                headers={"Authorization": f"Bearer {entry.data['token']}"},
                json={"message": message.strip(), "session_id": session_id},
                timeout=aiohttp.ClientTimeout(total=45),
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    return web.json_response({"status": "backend_unavailable"}, status=502)
                result = await response.json(content_type="application/json")
                if not isinstance(result, dict):
                    raise ValueError("Invalid chat response")
                reply = result.get("reply")
                if not isinstance(reply, str):
                    raise ValueError("Missing chat reply")
                return web.json_response({"reply": reply[:8000], "session_id": result.get("session_id") if isinstance(result.get("session_id"), str) and len(result["session_id"]) <= 64 else None}, headers={"Cache-Control": "no-store"})
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError):
            _LOGGER.debug("Declan native chat proxy request failed")
            return web.json_response({"status": "backend_unavailable"}, status=502)
