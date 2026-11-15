"""Admin-only Spotify playlist curation via Home Assistant's Declan Local service."""
import re

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.storage import Store

CATEGORIES = ("country", "braai", "romantic", "sexy_time", "rock", "afrikaans",
              "80s", "90s", "work_focus", "adhd_focus", "massage")
URI = re.compile(r"(?:spotify(?::|://)playlist[:/]|https://open\\.spotify\\.com/playlist/)([A-Za-z0-9]{22})(?:\\?[^#]*)?\\Z")


def canonical_playlist(value):
    if not isinstance(value, str):
        return None
    match = URI.fullmatch(value.strip())
    return "spotify://playlist/" + match.group(1) if match else None


class DeclanMusicPlaylistsView(HomeAssistantView):
    url = "/api/declan_two/music-playlists"
    name = "api:declan_two:music-playlists"
    requires_auth = True

    @staticmethod
    def authorised(request):
        user = request.get("hass_user")
        return user is not None and user.is_admin

    async def get(self, request):
        if not self.authorised(request):
            return web.json_response({"status": "forbidden"}, status=403)
        hass = request.app["hass"]
        if not hass.services.has_service("declan_local", "manage_music_playlist"):
            return web.json_response({"status": "declan_local_unavailable"}, status=503)
        saved = await Store(hass, 1, "jarvis_local.spotify_categories").async_load() or {}
        if not isinstance(saved, dict):
            saved = {}
        categories = {}
        for category in CATEGORIES:
            item = saved.get(category, {})
            item = item if isinstance(item, dict) else {}
            categories[category] = {
                key: list(dict.fromkeys(
                    canonical for value in (item.get(key) or [])[:250]
                    if (canonical := canonical_playlist(value))
                ))[:25 if key == "playlists" else 250]
                for key in ("playlists", "favourites", "excluded", "discovered")
            }
        return web.json_response({"categories": categories, "max_playlists": 25},
                                 headers={"Cache-Control": "no-store"})

    async def post(self, request):
        if not self.authorised(request):
            return web.json_response({"status": "forbidden"}, status=403)
        if request.content_type != "application/json" or request.content_length is None or not 0 < request.content_length <= 2048:
            return web.json_response({"status": "invalid_request"}, status=400)
        try:
            body = await request.json()
        except (ValueError, TypeError):
            return web.json_response({"status": "invalid_json"}, status=400)
        if not isinstance(body, dict) or set(body) != {"category", "playlist", "operation"}:
            return web.json_response({"status": "invalid_request"}, status=400)
        category = body["category"]
        playlist = canonical_playlist(body["playlist"])
        operation = body["operation"]
        if category not in CATEGORIES or playlist is None or operation not in ("add", "remove", "delete"):
            return web.json_response({"status": "invalid_request"}, status=400)
        hass = request.app["hass"]
        if not hass.services.has_service("declan_local", "manage_music_playlist"):
            return web.json_response({"status": "declan_local_unavailable"}, status=503)
        action = {"add": "favourite", "remove": "remove", "delete": "exclude"}[operation]
        try:
            await hass.services.async_call(
                "declan_local", "manage_music_playlist",
                {"category": category, "playlist": playlist, "operation": action},
                blocking=True, context=None,
            )
        except Exception:
            return web.json_response({"status": "playlist_update_failed"}, status=409)
        return await self.get(request)
