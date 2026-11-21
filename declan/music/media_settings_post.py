"""Authenticated media settings POST dispatch.

Called only after server.py's route, origin, content-type and payload gates.
"""
ROUTES = frozenset({
    "/api/settings/media-players",
    "/api/settings/music",
    "/api/settings/music-playlists",
    "/api/settings/spotify",
})


def handles(path):
    return path in ROUTES


def dispatch(handler, body, *, music, spotify_playlists,
             playlist_handler, opener_factory):
    if handler.path == "/api/settings/media-players":
        handler.approved_player_settings(body)
        return
    if handler.path == "/api/settings/music" and isinstance(body, dict) and set(body) == {"unblock_artist"}:
        # FUT-28: unblock an artist blocked with "don't play this artist again".
        from declan.music import music_extras
        name = body["unblock_artist"]
        if not isinstance(name, str) or not 0 < len(name) <= 200:
            handler.send_json(400, {"error": "Send the artist to unblock."})
            return
        try:
            handler.send_json(200, {"unblocked": music_extras.unblock_artist(name)})
        except OSError:
            handler.send_json(503, {"error": "Could not unblock the artist."})
        return
    if handler.path == "/api/settings/music":
        if not isinstance(body, dict) or "settings" not in body or not set(body) <= {"settings", "start_volume"}:
            handler.send_json(400, {"error": "Send music settings."})
            return
        try:
            result = music.music_settings.save(music.music_settings_path(), body["settings"],
                                               body.get("start_volume"))
        except ValueError as error:
            handler.send_json(400, {"error": str(error)})
            return
        except OSError:
            handler.send_json(503, {"error": "Could not save music settings."})
            return
        handler.send_json(200, result)
        return
    if handler.path == "/api/settings/music-playlists":
        playlist_handler(
            handler, body, credentials=music.spotify_credentials,
            start_refresh=spotify_playlists.start_refresh,
            manage=spotify_playlists.manage,
            opener_factory=opener_factory,
        )
        return
    if handler.path == "/api/settings/spotify":
        if not isinstance(body, dict):
            raise ValueError
        handler.spotify_settings(body)
        return
    raise ValueError("Unsupported media settings route")
