"""Admin-only, allowlisted native management operations. No credentials returned."""
import aiohttp
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

GET_PATHS = {
    "export": "/api/native/settings-export",
    "recovery": "/api/native/settings-recovery",
    "diagnostics": "/api/native/diagnostics",
    "intents": "/api/native/intents",
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
        path = ({"import": "/api/native/settings-import", "intents": "/api/native/intents", "spotify": "/api/native/spotify-credentials"}[operation] if body is not None else GET_PATHS[operation])
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
                if operation == "intents":
                    if body is not None:
                        return web.json_response({"saved": payload.get("saved") is True},
                                                 headers={"Cache-Control": "no-store"})
                    intents = payload.get("intents")
                    if not isinstance(intents, dict) or len(intents) > 500:
                        raise ValueError("Invalid intentions")
                    safe = {}
                    for phrase, target in intents.items():
                        if not isinstance(phrase, str) or not isinstance(target, str) or len(phrase) > 120 or len(target) > 120:
                            raise ValueError("Invalid intention")
                        safe[phrase] = target
                    return web.json_response({"intents": safe}, headers={"Cache-Control": "no-store"})
                if operation == "intents":
            if not isinstance(body, dict) or set(body) not in (
                {"phrase", "target", "previous"}, {"forget", "previous"}, {"turn_id", "target"}
            ):
                return web.json_response({"status": "invalid_request"}, status=400)
            if any(not isinstance(v, str) or not 0 < len(v) <= 120 for k, v in body.items() if k != "turn_id"):
                return web.json_response({"status": "invalid_request"}, status=400)
            if "turn_id" in body and (type(body["turn_id"]) is not int or not 0 < body["turn_id"] < 2**63):
                return web.json_response({"status": "invalid_request"}, status=400)
            return await self._relay(request, "intents", body)
        if operation == "import":
                    if body.get("confirm") is True:
                        return web.json_response({"saved": payload.get("saved") is True},
                                                 headers={"Cache-Control": "no-store"})
                    if not isinstance(payload.get("expected"), str) or not isinstance(payload.get("settings"), dict):
                        raise ValueError("Invalid preview")
                    return web.json_response({
                        "expected": payload["expected"], "settings": payload["settings"],
                        "learning_count": payload.get("learning_count", 0),
                        "replaces_learning": payload.get("replaces_learning", False),
                        "notice": payload.get("notice", ""),
                    }, headers={"Cache-Control": "no-store"})
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
        operation = request.match_info.get("operation")
        if operation not in {"spotify", "import", "intents"}:
            return web.json_response({"status": "invalid_operation"}, status=404)
        if request.content_type != "application/json" or request.content_length is None or not 0 < request.content_length <= (131072 if operation == "import" else 2048):
            return web.json_response({"status": "invalid_request"}, status=400)
        try:
            body = await request.json()
        except (ValueError, TypeError):
            return web.json_response({"status": "invalid_json"}, status=400)
        if operation == "import":
            if not isinstance(body, dict) or set(body) not in ({"document"}, {"document", "confirm", "expected"}):
                return web.json_response({"status": "invalid_request"}, status=400)
            if not isinstance(body.get("document"), dict):
                return web.json_response({"status": "invalid_document"}, status=400)
            if "confirm" in body and (body["confirm"] is not True or
                                      not isinstance(body.get("expected"), str) or len(body["expected"]) != 64):
                return web.json_response({"status": "preview_required"}, status=400)
            return await self._relay(request, "import", body)
        if not isinstance(body, dict) or set(body) != {"client_id", "client_secret", "confirm"} or body.get("confirm") is not True:
            return web.json_response({"status": "invalid_request"}, status=400)
        if not all(isinstance(body[key], str) and 0 < len(body[key]) <= 256 for key in ("client_id", "client_secret")):
            return web.json_response({"status": "invalid_credentials"}, status=400)
        return await self._relay(request, "spotify", body)
