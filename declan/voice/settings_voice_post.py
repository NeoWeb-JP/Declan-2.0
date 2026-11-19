"""Settings, media and voice management POST dispatch."""
from declan.http import operational_post_routes
from declan.ai import ai_settings_post
from declan.music import media_settings_post
from declan.voice import voice_post_routes
from declan.http import settings_import_post

ROUTES = frozenset({
    "/api/native/spotify-credentials", "/api/settings/ai",
    "/api/voicepipeline", "/api/voice-profiles",
    "/api/settings/import", "/api/native/settings-import",
})


def handles(path):
    return path in ROUTES or media_settings_post.handles(path)


def dispatch(handler, body, *, spotify_save, ai_replace_key, ai_save,
             ai_configured, music, spotify_playlists, playlist_handler,
             opener_factory, voice_manage, pipeline_error, profiles_manage,
             preview, apply):
    path = handler.path
    if path == "/api/native/spotify-credentials":
        operational_post_routes.handle_spotify_credentials(
            handler, body, save=spotify_save,
        )
    elif path == "/api/settings/ai":
        ai_settings_post.handle_ai_settings(
            handler, body, replace_key=ai_replace_key,
            save=ai_save, configured=ai_configured,
        )
    elif media_settings_post.handles(path):
        media_settings_post.dispatch(
            handler, body, music=music,
            spotify_playlists=spotify_playlists,
            playlist_handler=playlist_handler, opener_factory=opener_factory,
        )
    elif path == "/api/voicepipeline":
        voice_post_routes.handle_voicepipeline(
            handler, body, manage=voice_manage, pipeline_error=pipeline_error,
        )
    elif path == "/api/voice-profiles":
        voice_post_routes.handle_voice_profiles(
            handler, body, manage=profiles_manage,
        )
    elif path in {"/api/settings/import", "/api/native/settings-import"}:
        settings_import_post.handle_settings_import(
            handler, body, preview=preview, apply=apply,
        )
    else:
        raise ValueError("Unsupported settings/voice POST route")
