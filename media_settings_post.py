"""Authenticated media settings POST dispatch.

Called only after server.py's route, origin, content-type and payload gates.
"""
ROUTES = frozenset({
    "/api/settings/media-players",
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
