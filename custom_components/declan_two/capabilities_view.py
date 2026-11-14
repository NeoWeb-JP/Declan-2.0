"""Authenticated HA-side capability endpoint for the future native Declan panel.

The browser authenticates with Home Assistant, never with the Declan backend token.
"""
import logging

import aiohttp
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .compatibility import check_server_compatibility

_LOGGER = logging.getLogger(__name__)


class DeclanCapabilitiesView(HomeAssistantView):
    """Read-only server capability check, available only to signed-in HA users."""

    url = "/api/declan_two/capabilities"
    name = "api:declan_two:capabilities"
    requires_auth = True

    async def get(self, request):
        hass = request.app["hass"]
        entries = hass.config_entries.async_entries("declan_two")
        if len(entries) != 1:
            return web.json_response(
                {"status": "not_configured" if not entries else "multiple_entries"},
                status=503,
                headers={"Cache-Control": "no-store"},
            )
        entry = entries[0]
        try:
            async with async_get_clientsession(hass).get(
                entry.data["url"] + "/api/capabilities",
                headers={"Authorization": f"Bearer {entry.data['token']}"},
                timeout=aiohttp.ClientTimeout(total=5),
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    return web.json_response(
                        {"status": "backend_unavailable"},
                        status=502,
                        headers={"Cache-Control": "no-store"},
                    )
                payload = await response.json(content_type="application/json")
                if not isinstance(payload, dict):
                    raise ValueError("Expected capabilities object")
                compatibility = check_server_compatibility(payload)
                return web.json_response({
                    "status": "connected" if compatibility.compatible else "incompatible",
                    "compatible": compatibility.compatible,
                    "api_version": compatibility.api_version,
                    "server_version": compatibility.server_version,
                    "reason": compatibility.reason,
                    "capabilities": payload.get("capabilities", [])
                    if isinstance(payload.get("capabilities"), list)
                    and all(isinstance(item, str) for item in payload["capabilities"]) else [],
                }, status=200 if compatibility.compatible else 502,
                    headers={"Cache-Control": "no-store"})
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError):
            _LOGGER.debug("Declan capabilities request failed")
            return web.json_response(
                {"status": "backend_unavailable"},
                status=502,
                headers={"Cache-Control": "no-store"},
            )
