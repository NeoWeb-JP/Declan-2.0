"""Authenticated bounded PCM microphone relay for the native HA panel."""
import logging
import aiohttp
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)
MAX_BYTES = 640000

class DeclanMicrophoneView(HomeAssistantView):
    url = "/api/declan_two/microphone"
    name = "api:declan_two:microphone"
    requires_auth = True

    async def post(self, request):
        user = request.get("hass_user")
        if user is None or not user.is_admin:
            return web.json_response({"status": "forbidden"}, status=403)
        if request.content_type != "application/octet-stream":
            return web.json_response({"status": "invalid_content_type"}, status=415)
        size = request.content_length
        if size is None or not 0 < size <= MAX_BYTES or size % 2:
            return web.json_response({"status": "invalid_size"}, status=413)
        entries = request.app["hass"].config_entries.async_entries("declan_two")
        if len(entries) != 1:
            return web.json_response({"status": "not_configured"}, status=503)
        audio = await request.content.read(MAX_BYTES + 1)
        if len(audio) != size:
            return web.json_response({"status": "invalid_size"}, status=413)
        entry = entries[0]
        try:
            async with async_get_clientsession(request.app["hass"]).post(
                entry.data["url"].rstrip("/") + "/api/stt",
                data=audio,
                headers={"Authorization": f"Bearer {entry.data['token']}",
                         "Content-Type": "application/octet-stream"},
                timeout=aiohttp.ClientTimeout(total=35),
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    return web.json_response({"status": "transcription_failed"}, status=502)
                payload = await response.json(content_type="application/json")
                transcript = payload.get("text") if isinstance(payload, dict) else None
                if not isinstance(transcript, str) or len(transcript) > 1000:
                    raise ValueError("Invalid transcript")
                return web.json_response({"text": transcript}, headers={"Cache-Control": "no-store"})
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError):
            _LOGGER.warning("Native microphone transcription unavailable")
            return web.json_response({"status": "transcription_unavailable"}, status=502)
