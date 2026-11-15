"""Admin-only read-only conversation history proxy for the native HA panel."""
import logging
import re

import aiohttp
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)


class DeclanHistoryView(HomeAssistantView):
    url = "/api/declan_two/history"
    name = "api:declan_two:history"
    requires_auth = True

    async def get(self, request):
        user = request.get("hass_user")
        if user is None or not user.is_admin:
            return web.json_response({"status": "forbidden"}, status=403)
        hass = request.app["hass"]
        entries = hass.config_entries.async_entries("declan_two")
        if len(entries) != 1:
            return web.json_response({"status": "not_configured"}, status=503)
        recording_ids = request.query.get("recording_ids")
        if recording_ids is not None:
            identifiers = recording_ids.split(",")
            if (not 1 <= len(identifiers) <= 100 or any(
                not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value) for value in identifiers
            )):
                return web.json_response({"status": "invalid_recording_ids"}, status=400)
            entry = entries[0]
            try:
                async with async_get_clientsession(hass).get(
                    entry.data["url"] + "/api/history/recording-links?ids=" + recording_ids,
                    headers={"Authorization": f"Bearer {entry.data['token']}"},
                    timeout=aiohttp.ClientTimeout(total=8),
                    allow_redirects=False,
                ) as response:
                    if response.status != 200:
                        return web.json_response({"status": "backend_unavailable"}, status=502)
                    payload = await response.json(content_type="application/json")
                    links = payload.get("links") if isinstance(payload, dict) else None
                    if not isinstance(links, dict):
                        raise ValueError("Invalid recording links")
                    verified = {key: value for key, value in links.items()
                                if key in identifiers and type(value) is int and value > 0}
                    return web.json_response({"links": verified}, headers={"Cache-Control": "no-store"})
            except (aiohttp.ClientError, TimeoutError, ValueError, TypeError):
                return web.json_response({"status": "backend_unavailable"}, status=502)
        before = request.query.get("before")
        if before is not None and (not before.isascii() or not before.isdecimal()
                                   or not 0 < int(before) < 2**63):
            return web.json_response({"status": "invalid_cursor"}, status=400)
        entry = entries[0]
        path = "/api/history" + (f"?before={before}" if before else "")
        try:
            async with async_get_clientsession(hass).get(
                entry.data["url"] + path,
                headers={"Authorization": f"Bearer {entry.data['token']}"},
                timeout=aiohttp.ClientTimeout(total=8),
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    return web.json_response({"status": "backend_unavailable"}, status=502)
                payload = await response.json(content_type="application/json")
                if not isinstance(payload, dict) or not isinstance(payload.get("turns"), list):
                    raise ValueError("Invalid history payload")
                # Return only display fields. Never pass learning, metadata or credentials.
                turns = []
                for item in payload["turns"][:50]:
                    if not isinstance(item, dict):
                        continue
                    turns.append({
                        "id": item.get("id") if type(item.get("id")) is int else None,
                        "message": str(item.get("message") or "")[:1000],
                        "reply": str(item.get("reply") or "")[:4000],
                        "source": str(item.get("source") or "")[:50],
                        "teachable": item.get("teachable") is True,
                        "action_results": [{
                            "entity_id": str(step.get("entity_id") or "")[:120],
                            "action": str(step.get("action") or "")[:80],
                            "status": str(step.get("status") or "")[:60],
                            "detail": str(step.get("detail") or "")[:240],
                            "ai_generated": step.get("ai_generated") is True,
                        } for step in (item.get("action_results") or [])[:8]
                            if isinstance(step, dict)],
                    })
                next_cursor = payload.get("next")
                return web.json_response({
                    "turns": turns,
                    "next": next_cursor if type(next_cursor) is int and next_cursor > 0 else None,
                }, headers={"Cache-Control": "no-store"})
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError):
            _LOGGER.debug("Declan history proxy request failed")
            return web.json_response({"status": "backend_unavailable"}, status=502)
