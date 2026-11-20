"""Explicit POST endpoint allowlist and 404 response boundary."""

POST_ROUTES = frozenset({
    "/api/assist", "/api/assist/history", "/api/chat", "/api/settings/spotify",
    "/api/tts", "/api/stt", "/api/updates", "/api/history/clear",
    "/api/history/intents", "/api/settings/import", "/api/settings/media-players",
    "/api/settings/music-playlists", "/api/settings/ai", "/api/voice-profiles",
    "/api/settings/music", "/api/settings/speaker", "/api/settings/command-style", "/api/settings/chat",
    "/api/voicepipeline", "/api/native/spotify-credentials",
    "/api/native/settings-import", "/api/native/intents", "/api/native/routines",
    "/api/native/routine-responses",
})


def enforce_known_route(handler):
    if handler.path not in POST_ROUTES:
        handler.send_json(404, {"error": "Not found."})
        return False
    return True
