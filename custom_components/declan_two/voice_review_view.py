"""Read-only admin voice review through Home Assistant."""
import logging

import aiohttp
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)


class DeclanVoiceReviewView(HomeAssistantView):
    url = "/api/declan_two/voice-review"
    name = "api:declan_two:voice-review"
    requires_auth = True

    async def get(self, request):
        user = request.get("hass_user")
        if user is None or not user.is_admin:
            return web.json_response({"status": "forbidden"}, status=403)
        hass = request.app["hass"]
        entries = hass.config_entries.async_entries("declan_two")
        if len(entries) != 1:
            return web.json_response({"status": "not_configured"}, status=503)
        entry = entries[0]
        try:
            async with async_get_clientsession(hass).get(
                entry.data["url"] + "/api/voicepipeline",
                headers={"Authorization": f"Bearer {entry.data['token']}"},
                timeout=aiohttp.ClientTimeout(total=15),
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    return web.json_response({"status": "backend_unavailable"}, status=502)
                data = await response.json(content_type="application/json")
                if not isinstance(data, dict) or not isinstance(data.get("profiles"), list) or not isinstance(data.get("interactions"), list):
                    raise ValueError("Invalid VoicePipeline response")
                profiles = []
                for row in data["profiles"][:100]:
                    if not isinstance(row, dict):
                        continue
                    profiles.append({
                        "name": str(row.get("name") or "")[:80],
                        "reference_clip_count": row.get("reference_clip_count") if type(row.get("reference_clip_count")) is int else None,
                        "interaction_count": row.get("interaction_count") if type(row.get("interaction_count")) is int else None,
                        "avg_confidence": row.get("avg_confidence") if type(row.get("avg_confidence")) in (int, float) else None,
                    })
                interactions = []
                for row in data["interactions"][:100]:
                    if not isinstance(row, dict):
                        continue
                    interactions.append({
                        "transcript": str(row.get("transcript") or "")[:1000],
                        "matched_speaker": str(row.get("matched_speaker") or "")[:80],
                        "match_confidence": row.get("match_confidence") if type(row.get("match_confidence")) in (int, float) else None,
                        "status": str(row.get("status") or "")[:50],
                    })
                return web.json_response({
                    "profiles": profiles, "interactions": interactions,
                    "notice": "Read-only preview. Use the existing Declan app to review, correct or enrol recordings.",
                }, headers={"Cache-Control": "no-store"})
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError):
            _LOGGER.debug("Declan voice review proxy failed")
            return web.json_response({"status": "backend_unavailable"}, status=502)
