"""Admin-only proxy for approved Music Assistant player mappings."""
import logging

import aiohttp
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)


class DeclanMediaPlayersView(HomeAssistantView):
    url = "/api/declan_two/media-players"
    name = "api:declan_two:media-players"
    requires_auth = True

    async def get(self, request):
        return await self._relay(request)

    async def post(self, request):
        if request.content_type != "application/json":
            return web.json_response({"status": "invalid_content_type"}, status=415)
        if request.content_length is None or not 0 < request.content_length <= 8192:
            return web.json_response({"status": "invalid_size"}, status=413)
        try:
            body = await request.json()
        except (ValueError, TypeError):
            return web.json_response({"status": "invalid_json"}, status=400)
        if not isinstance(body, dict) or set(body) != {"rooms"} or not isinstance(body["rooms"], dict):
            return web.json_response({"status": "invalid_mapping"}, status=400)
        rooms = body["rooms"]
        if len(rooms) > 100 or any(
            not isinstance(k, str) or not 0 < len(k) <= 128
            or not isinstance(v, str) or not v.startswith("media_player.") or len(v) > 255
            for k, v in rooms.items()
        ):
            return web.json_response({"status": "invalid_mapping"}, status=400)
        return await self._relay(request, {"rooms": rooms})

    async def _relay(self, request, body=None):
        user = request.get("hass_user")
        if user is None or not user.is_admin:
            return web.json_response({"status": "forbidden"}, status=403)
        hass = request.app["hass"]
        entries = hass.config_entries.async_entries("declan_two")
        if len(entries) != 1:
            return web.json_response({"status": "not_configured"}, status=503)
        entry = entries[0]
        try:
            session = async_get_clientsession(hass)
            kwargs = {
                "headers": {"Authorization": f"Bearer {entry.data['token']}"},
                "timeout": aiohttp.ClientTimeout(total=15),
                "allow_redirects": False,
            }
            url = entry.data["url"] + "/api/settings/media-players"
            async with (session.post(url, json=body, **kwargs) if body is not None
                        else session.get(url, **kwargs)) as response:
                if response.status != 200:
                    return web.json_response(
                        {"status": "invalid_mapping" if response.status == 400 else "backend_unavailable"},
                        status=400 if response.status == 400 else 502,
                        headers={"Cache-Control": "no-store"},
                    )
                payload = await response.json(content_type="application/json")
                if not isinstance(payload, dict) or not isinstance(payload.get("rooms"), list) or not isinstance(payload.get("players"), list) or not isinstance(payload.get("selected"), dict):
                    raise ValueError("Invalid player inventory")
                # Explicit field selection: do not expose backend credentials or metadata.
                players = []
                for player in payload["players"][:250]:
                    if not isinstance(player, dict) or not isinstance(player.get("entity_id"), str):
                        continue
                    players.append({
                        "entity_id": player["entity_id"][:255],
                        "name": str(player.get("name") or player["entity_id"])[:200],
                        "area": str(player.get("area") or "")[:200],
                        "state": str(player.get("state") or "")[:60],
                    })
                rooms = [room for room in payload["rooms"][:100] if isinstance(room, str) and len(room) <= 128]
                selected = {key: value for key, value in payload["selected"].items()
                            if key in rooms and isinstance(value, str)
                            and any(p["entity_id"] == value for p in players)}
                return web.json_response({
                    "configured": payload.get("configured") is True,
                    "rooms": rooms, "selected": selected, "players": players,
                }, headers={"Cache-Control": "no-store"})
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError):
            _LOGGER.debug("Declan approved players proxy failed")
            return web.json_response({"status": "backend_unavailable"}, status=502,
                                     headers={"Cache-Control": "no-store"})
