"""Authenticated bounded PCM microphone relay for the native HA panel."""
import logging
import base64
import binascii
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
        if request.content_type != "application/json":
            return web.json_response({"status": "invalid_content_type"}, status=415)
        size = request.content_length
        if size is None or not 0 < size <= 900000:
            return web.json_response({"status": "invalid_size"}, status=413)
        entries = request.app["hass"].config_entries.async_entries("declan_two")
        if len(entries) != 1:
            return web.json_response({"status": "not_configured"}, status=503)
        try:
            body = await request.json()
            if not isinstance(body, dict) or set(body) != {"audio"} or not isinstance(body["audio"], str):
                raise ValueError("Invalid audio")
            audio = base64.b64decode(body["audio"], validate=True)
        except (ValueError, TypeError, binascii.Error):
            return web.json_response({"status": "invalid_audio"}, status=400)
        if not 0 < len(audio) <= MAX_BYTES or len(audio) % 2:
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
