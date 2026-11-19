"""Authorised playlist-management POST response adapter.

HTTP authentication, JSON decoding and request limits remain in server.py.
"""


def handle_music_playlists(handler, body, *, credentials, start_refresh, manage, opener_factory):
    try:
        if (isinstance(body, dict) and set(body) == {"category", "operation"}
                and body.get("operation") == "refresh"):
            spotify_credentials, _ = credentials()
            if not all(spotify_credentials):
                handler.send_json(409, {
                    "error": "Configure Spotify credentials before refreshing playlists.",
                })
                return
            handler.send_json(200, start_refresh(body["category"], opener_factory))
        else:
            handler.send_json(200, manage(body))
    except ValueError as error:
        handler.send_json(400, {"error": str(error)})
    except OSError:
        handler.send_json(503, {"error": "Spotify playlist storage unavailable."})
