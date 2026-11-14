"""Admin-only, authenticated bridge to Declan's existing backend updater."""
import re
import logging
from pathlib import Path
import json

from .compatibility import check_server_compatibility
import aiohttp
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)
VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.]+)?$")


class DeclanUpdatesView(HomeAssistantView):
    url = "/api/declan_two/updates"
    name = "api:declan_two:updates"
    requires_auth = True

    async def get(self, request):
        response = await self._relay(request, "GET", "/api/updates/status")
        if response.status == 200:
            # Manifest is the installed HACS integration version, not the backend version.
            manifest = json.loads((Path(__file__).parent / "manifest.json").read_text())
            payload = json.loads(response.body)
            payload["integration_version"] = manifest["version"]
            return web.json_response(payload, headers={"Cache-Control": "no-store"})
        return response

    async def post(self, request):
        if request.content_type != "application/json":
            return web.json_response({"status": "invalid_content_type"}, status=415)
        if request.content_length is None or not 0 < request.content_length <= 512:
            return web.json_response({"status": "invalid_size"}, status=413)
        try:
            body = await request.json()
        except (ValueError, TypeError):
            return web.json_response({"status": "invalid_json"}, status=400)
        if not isinstance(body, dict) or type(body.get("include_prereleases")) is not bool:
            return web.json_response({"status": "invalid_request"}, status=400)
        if body.get("operation") == "check" and set(body) == {"operation", "include_prereleases"}:
            return await self._relay(request, "POST", "/api/updates", body)
        if (body.get("operation") == "install" and set(body) == {"operation", "include_prereleases", "version"}
                and isinstance(body["version"], str) and VERSION.fullmatch(body["version"])):
            return await self._relay(request, "POST", "/api/updates", {
                "version": body["version"], "include_prereleases": body["include_prereleases"]
            })
        return web.json_response({"status": "invalid_request"}, status=400)

    async def _relay(self, request, method, path, body=None):
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
                "timeout": aiohttp.ClientTimeout(total=25),
                "allow_redirects": False,
            }
            base = entry.data["url"].rstrip("/")
            if method == "POST":
                async with session.get(base + "/api/capabilities", **kwargs) as capability_response:
                    if capability_response.status != 200:
                        return web.json_response({"status": "compatibility_check_failed"}, status=502)
                    capabilities = await capability_response.json(content_type="application/json")
                    if not isinstance(capabilities, dict):
                        raise ValueError("Invalid capabilities response")
                    check = check_server_compatibility(capabilities)
                    if not check.compatible or not isinstance(capabilities.get("capabilities"), list) or "updates" not in capabilities["capabilities"]:
                        return web.json_response({"status": "backend_incompatible", "reason": check.reason}, status=409)
            url = base + path
            async with (session.post(url, json=body, **kwargs) if method == "POST"
                        else session.get(url, **kwargs)) as response:
                if response.status not in (200, 202, 409, 503):
                    return web.json_response({"status": "backend_unavailable"}, status=502)
                payload = await response.json(content_type="application/json")
                if not isinstance(payload, dict):
                    raise ValueError("Invalid update response")
                return web.json_response(payload, status=response.status,
                                         headers={"Cache-Control": "no-store"})
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError):
            _LOGGER.warning("Declan update request failed")
            return web.json_response({"status": "backend_unavailable"}, status=502,
                                     headers={"Cache-Control": "no-store"})
