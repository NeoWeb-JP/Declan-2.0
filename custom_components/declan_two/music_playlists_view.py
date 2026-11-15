"""Admin-only native Declan 2.0 Spotify playlist settings proxy."""
import aiohttp
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

CATEGORIES = ("country", "braai", "romantic", "sexy_time", "rock", "afrikaans",
              "80s", "90s", "work_focus", "adhd_focus", "massage")


class DeclanMusicPlaylistsView(HomeAssistantView):
    url = "/api/declan_two/music-playlists"
    name = "api:declan_two:music-playlists"
    requires_auth = True

    async def get(self, request):
        return await self._relay(request)

    async def post(self, request):
        if request.content_type != "application/json" or request.content_length is None or not 0 < request.content_length <= 2048:
            return web.json_response({"status": "invalid_request"}, status=400)
        try:
            body = await request.json()
        except (ValueError, TypeError):
            return web.json_response({"status": "invalid_json"}, status=400)
        if not isinstance(body, dict) or set(body) != {"category", "playlist", "operation"}:
            return web.json_response({"status": "invalid_request"}, status=400)
        if body["category"] not in CATEGORIES or body["operation"] not in ("add", "remove", "delete") or not isinstance(body["playlist"], str) or len(body["playlist"]) > 256:
            return web.json_response({"status": "invalid_request"}, status=400)
        return await self._relay(request, body)

    async def _relay(self, request, body=None):
        user = request.get("hass_user")
        if user is None or not user.is_admin:
            return web.json_response({"status": "forbidden"}, status=403)
        hass = request.app["hass"]
        entries = hass.config_entries.async_entries("declan_two")
        if len(entries) != 1:
            return web.json_response({"status": "not_configured"}, status=503)
        entry = entries[0]
        url = entry.data["url"] + "/api/settings/music-playlists"
        kwargs = {
            "headers": {"Authorization": f"Bearer {entry.data['token']}"},
            "timeout": aiohttp.ClientTimeout(total=15),
            "allow_redirects": False,
        }
        try:
            session = async_get_clientsession(hass)
            async with (session.post(url, json=body, **kwargs) if body is not None
                        else session.get(url, **kwargs)) as response:
                if response.status != 200:
                    return web.json_response({"status": "invalid_request" if response.status == 400 else "backend_unavailable"},
                                             status=400 if response.status == 400 else 502)
                payload = await response.json(content_type="application/json")
                if not isinstance(payload, dict) or not isinstance(payload.get("categories"), dict):
                    raise ValueError("Invalid Spotify playlist catalogue")
                categories = {}
                for name in CATEGORIES:
                    item = payload["categories"].get(name, {})
                    if not isinstance(item, dict):
                        item = {}
                    categories[name] = {
                        field: [uri for uri in (item.get(field) or [])[:250]
                                if isinstance(uri, str) and uri.startswith("spotify://playlist/") and len(uri) == 41]
                        for field in ("playlists", "favourites", "excluded", "discovered")
                    }
                return web.json_response({"categories": categories, "max_playlists": 25},
                                         headers={"Cache-Control": "no-store"})
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError):
            return web.json_response({"status": "backend_unavailable"}, status=502)
