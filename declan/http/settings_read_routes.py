"""Read-only voice, diagnostics, and AI/media settings routes."""
import sqlite3

ROUTES = frozenset({
    "/api/voicepipeline", "/api/voice-profiles", "/api/diagnostics", "/api/diagnostics/metrics",
    "/api/settings/spotify", "/api/settings/ai",
    "/api/settings/media-players", "/api/settings/music-playlists",
    "/api/settings/music", "/api/settings/speaker",
    "/api/settings/command-style",
    "/api/settings/chat",
    "/api/settings/household",
})


def handles(path):
    return path in ROUTES


def dispatch(handler, *, voicepipeline, voice_profiles, diagnostics, history,
             ai_budget, ai_settings, ai_credentials, spotify_playlists):
    path = handler.path
    if path == "/api/voicepipeline":
        try:
            handler.send_json(200, voicepipeline.listing())
        except voicepipeline.PipelineError as error:
            handler.send_json(error.status, {"error": str(error)})
    elif path == "/api/voice-profiles":
        try:
            handler.send_json(200, voice_profiles.listing())
        except (OSError, sqlite3.Error):
            handler.send_json(503, {"error": "Voice profiles are unavailable."})
    elif path == "/api/diagnostics/metrics":
        try:
            handler.send_json(200, {"metrics": diagnostics.metrics()})
        except (OSError, sqlite3.Error, ValueError):
            handler.send_json(503, {"error": "Diagnostic metrics unavailable."})
    elif path == "/api/diagnostics":
        try:
            handler.send_json(200, {"traces": diagnostics.recent()})
        except (OSError, sqlite3.Error, ValueError):
            handler.send_json(503, {"error": "Diagnostics are unavailable."})
    elif path == "/api/settings/spotify":
        handler.spotify_settings()
    elif path == "/api/settings/ai":
        try:
            with history.database() as db:
                usage_micro_usd = ai_budget.monthly_reserved(db)
            handler.send_json(200, {"settings": ai_settings.read(),
                                    "key_configured": ai_credentials.configured(),
                                    "month_usage_micro_usd": usage_micro_usd})
        except (OSError, sqlite3.Error, ValueError):
            handler.send_json(503, {"error": "AI settings unavailable."})
    elif path == "/api/settings/music":
        from declan.music import music, music_extras
        payload = music.music_settings.listing(music.music_settings_path())
        try:
            payload["blocked_artists"] = sorted(music_extras.blocked_artists().values(), key=str.casefold)
        except (OSError, sqlite3.Error):
            payload["blocked_artists"] = None
        handler.send_json(200, payload)
    elif path == "/api/settings/command-style":
        from declan.turn import command_style
        handler.send_json(200, command_style.listing())
    elif path == "/api/settings/chat":
        from declan.ai import general_chat
        handler.send_json(200, general_chat.listing())
    elif path == "/api/settings/household":
        from declan.turn import household_settings, line_freshness
        payload = household_settings.listing()
        try:
            payload["generated"] = line_freshness.listing()
        except (OSError, ValueError, sqlite3.Error):
            payload["generated"] = None
        from declan.turn import whereabouts
        try:
            payload["whereabouts"] = whereabouts.listing()
        except (OSError, sqlite3.Error):
            payload["whereabouts"] = None
        from declan.turn import usual
        try:
            payload["usuals"] = usual.listing()
        except (OSError, ValueError, sqlite3.Error):
            payload["usuals"] = None
        from declan.ha import entrance_themes
        try:
            payload["themes"] = entrance_themes.listing()
        except (OSError, ValueError, sqlite3.Error):
            payload["themes"] = None
        from declan.ha import house_info
        try:
            payload["house_info"] = house_info.listing()
        except (OSError, ValueError):
            payload["house_info"] = None
        handler.send_json(200, payload)
    elif path == "/api/settings/speaker":
        from declan.voice import speaker_settings
        handler.send_json(200, speaker_settings.listing())
    elif path == "/api/settings/media-players":
        handler.approved_player_settings()
    elif path == "/api/settings/music-playlists":
        try:
            handler.send_json(200, spotify_playlists.listing())
        except (OSError, ValueError):
            handler.send_json(503, {"error": "Spotify playlists unavailable."})
    else:
        raise ValueError("Unsupported settings read route")
