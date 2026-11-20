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
    "/api/settings/speaker", "/api/settings/command-style", "/api/settings/chat",
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
    elif path == "/api/settings/command-style":
        from declan.turn import command_style
        if not isinstance(body, dict) or set(body) != {"settings"}:
            handler.send_json(400, {"error": "Send command style settings."})
            return
        try:
            handler.send_json(200, command_style.save(body["settings"]))
        except ValueError as error:
            handler.send_json(400, {"error": str(error)})
        except OSError:
            handler.send_json(503, {"error": "Could not save the command style."})
    elif path == "/api/settings/chat":
        from declan.ai import general_chat
        if not isinstance(body, dict) or set(body) != {"settings"}:
            handler.send_json(400, {"error": "Send general chat settings."})
            return
        try:
            general_chat.save(body["settings"])
            handler.send_json(200, general_chat.listing())
        except ValueError as error:
            handler.send_json(400, {"error": str(error)})
        except OSError:
            handler.send_json(503, {"error": "Could not save general chat settings."})
    elif path == "/api/settings/speaker":
        from declan.voice import speaker_settings
        if not isinstance(body, dict) or set(body) != {"settings"}:
            handler.send_json(400, {"error": "Send speaker settings."})
            return
        try:
            handler.send_json(200, speaker_settings.save(body["settings"]))
        except ValueError as error:
            handler.send_json(400, {"error": str(error)})
        except OSError:
            handler.send_json(503, {"error": "Could not save speaker settings."})
    elif path in {"/api/settings/import", "/api/native/settings-import"}:
        settings_import_post.handle_settings_import(
            handler, body, preview=preview, apply=apply,
        )
    else:
        raise ValueError("Unsupported settings/voice POST route")
