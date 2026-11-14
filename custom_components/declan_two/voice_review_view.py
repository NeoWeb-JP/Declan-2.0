"""Read-only admin voice review through Home Assistant."""
import logging
import re

import aiohttp
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)


class DeclanVoiceReviewView(HomeAssistantView):
    url = "/api/declan_two/voice-review"
    name = "api:declan_two:voice-review"
    requires_auth = True

    async def post(self, request):
        user = request.get("hass_user")
        if user is None or not user.is_admin:
            return web.json_response({"status": "forbidden"}, status=403)
        if request.content_type != "application/json":
            return web.json_response({"status": "invalid_content_type"}, status=415)
        if request.content_length is None or not 0 < request.content_length <= 2048:
            return web.json_response({"status": "invalid_size"}, status=413)
        try:
            body = await request.json()
        except (ValueError, TypeError):
            return web.json_response({"status": "invalid_json"}, status=400)
        if not isinstance(body, dict) or body.get("operation") not in {"resolve", "audio", "correct"}:
            return web.json_response({"status": "invalid_operation"}, status=400)
        operation = body["operation"]
        action = body.get("action")
        interaction_id = body.get("interaction_id")
        if operation == "audio":
            if set(body) != {"operation", "interaction_id"} or not isinstance(interaction_id, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,80}", interaction_id) is None:
                return web.json_response({"status": "invalid_operation"}, status=400)
        elif body.get("confirm") is not True:
            return web.json_response({"status": "invalid_operation"}, status=400)
        if operation == "resolve" and (action not in {"confirm", "assign", "dismiss", "enrol"} or not isinstance(interaction_id, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,80}", interaction_id) is None):
            return web.json_response({"status": "invalid_operation"}, status=400)
        if operation == "correct":
            expected = body.get("expected_resolution_id")
            if (set(body) != {"operation", "interaction_id", "assigned_to", "expected_resolution_id", "confirm"}
                    or not isinstance(interaction_id, str)
                    or re.fullmatch(r"[A-Za-z0-9_-]{1,80}", interaction_id) is None
                    or (expected is not None and
                        (not isinstance(expected, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,80}", expected) is None))):
                return web.json_response({"status": "invalid_operation"}, status=400)
        name = body.get("assigned_to")
        if operation == "audio":
            pass
        elif action == "dismiss":
            if name is not None:
                return web.json_response({"status": "invalid_speaker"}, status=400)
        elif not isinstance(name, str) or not re.fullmatch(r"[^\W\d_][\w '\u2019-]{0,39}", name) or name.casefold() in {"unknown", "unidentified", "none"}:
            return web.json_response({"status": "invalid_speaker"}, status=400)
        if operation == "resolve" and set(body) - {"operation", "action", "interaction_id", "assigned_to", "confirm"}:
            return web.json_response({"status": "invalid_operation"}, status=400)
        hass = request.app["hass"]
        entries = hass.config_entries.async_entries("declan_two")
        if len(entries) != 1:
            return web.json_response({"status": "not_configured"}, status=503)
        entry = entries[0]
        try:
            async with async_get_clientsession(hass).post(
                entry.data["url"] + "/api/voicepipeline",
                headers={"Authorization": f"Bearer {entry.data['token']}"},
                json=({"operation": "audio", "interaction_id": interaction_id} if operation == "audio" else
                      {"operation": "correct", "interaction_id": interaction_id,
                       "assigned_to": name, "expected_resolution_id": body["expected_resolution_id"],
                       "confirm": True} if operation == "correct" else
                      {"operation": "resolve", "action": action,
                       "interaction_id": interaction_id, "assigned_to": name, "confirm": True}),
                timeout=aiohttp.ClientTimeout(total=20),
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    return web.json_response({"status": "conflict" if response.status == 409 else "review_failed"},
                                             status=409 if response.status == 409 else 502,
                                             headers={"Cache-Control": "no-store"})
                result = await response.json(content_type="application/json")
                if operation == "audio":
                    import base64
                    encoded = result.get("audio") if isinstance(result, dict) else None
                    if not isinstance(encoded, str) or len(encoded) > 6_000_000:
                        raise ValueError("Invalid audio response")
                    raw = base64.b64decode(encoded, validate=True)
                    if len(raw) < 12 or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
                        raise ValueError("Invalid WAV")
                    return web.json_response({"audio": encoded}, headers={"Cache-Control": "no-store"})
                if not isinstance(result, dict) or result.get("saved") is not True:
                    raise ValueError("Missing save confirmation")
                return web.json_response({"saved": True}, headers={"Cache-Control": "no-store"})
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError, __import__("binascii").Error):
            _LOGGER.debug("Declan voice match update failed")
            return web.json_response({"status": "review_failed"}, status=502,
                                     headers={"Cache-Control": "no-store"})

    async def get(self, request):
        user = request.get("hass_user")
        if user is None or not user.is_admin:
            return web.json_response({"status": "forbidden"}, status=403)
        hass = request.app["hass"]
        entries = hass.config_entries.async_entries("declan_two")
        if len(entries) != 1:
            return web.json_response({"status": "not_configured"}, status=503)
        entry = entries[0]
        history = request.query.get("history") == "1"
        if request.query and (set(request.query) != {"history"} or not history):
            return web.json_response({"status": "invalid_query"}, status=400)
        try:
            if history:
                async with async_get_clientsession(hass).post(
                    entry.data["url"] + "/api/voicepipeline",
                    headers={"Authorization": f"Bearer {entry.data['token']}"},
                    json={"operation": "history"},
                    timeout=aiohttp.ClientTimeout(total=15),
                    allow_redirects=False,
                ) as response:
                    if response.status != 200:
                        return web.json_response({"status": "backend_unavailable"}, status=502)
                    data = await response.json(content_type="application/json")
                    if not isinstance(data, dict) or not isinstance(data.get("interactions"), list):
                        raise ValueError("Invalid VoicePipeline history")
                    rows = []
                    for row in data["interactions"][:100]:
                        if not isinstance(row, dict):
                            continue
                        rows.append({
                            "id": row.get("id") if isinstance(row.get("id"), str) and len(row["id"]) <= 80 else None,
                            "transcript": str(row.get("transcript") or "")[:1000],
                            "matched_speaker": str(row.get("matched_speaker") or "")[:80],
                            "current_assigned_to": str(row.get("current_assigned_to") or "")[:80],
                            "status": str(row.get("status") or "")[:50],
                            "match_confidence": row.get("match_confidence") if type(row.get("match_confidence")) in (int, float) else None,
                            "recorded_at": str(row.get("recorded_at") or "")[:50],
                            "current_resolution_id": row.get("current_resolution_id") if isinstance(row.get("current_resolution_id"), str) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", row["current_resolution_id"]) else None,
                        })
                    return web.json_response({"interactions": rows}, headers={"Cache-Control": "no-store"})
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
                        "id": row.get("id") if isinstance(row.get("id"), str) and len(row["id"]) <= 80 else None,
                        "transcript": str(row.get("transcript") or "")[:1000],
                        "recorded_at": str(row.get("recorded_at") or "")[:50],
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
