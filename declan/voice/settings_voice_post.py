"""Settings, media and voice management POST dispatch."""
import sqlite3
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
    "/api/settings/household",
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
    elif path == "/api/settings/household":
        from declan.turn import household_settings, line_freshness
        if isinstance(body, dict) and set(body) == {"delete_line"} and isinstance(body["delete_line"], dict):
            # FUT-61: remove one generated line from Settings -> Household.
            target = body["delete_line"]
            try:
                removed = line_freshness.delete(target.get("key"), target.get("line"))
            except ValueError as error:
                handler.send_json(400, {"error": str(error)})
                return
            except (OSError, sqlite3.Error):
                handler.send_json(503, {"error": "Could not delete the line."})
                return
            handler.send_json(200, {"deleted": removed})
            return
        if isinstance(body, dict) and set(body) == {"save_personality"}:
            # Personality sliders for the household and guests; a change forgets learned lines.
            from declan.turn import personality_dials
            try:
                saved = personality_dials.save(body["save_personality"])
            except ValueError as error:
                handler.send_json(400, {"error": str(error)})
                return
            except (OSError, sqlite3.Error):
                handler.send_json(503, {"error": "Could not save the personality sliders."})
                return
            handler.send_json(200, {"saved": True, "personality": saved})
            return
        if isinstance(body, dict) and set(body) == {"forget_item"} and isinstance(body["forget_item"], str):
            # FUT-42: remove one "where did I put" entry from Settings -> Household.
            from declan.turn import whereabouts
            try:
                removed = whereabouts.forget(body["forget_item"])
            except (OSError, sqlite3.Error):
                handler.send_json(503, {"error": "Could not forget that."})
                return
            handler.send_json(200, {"forgotten": removed is not None})
            return
        if isinstance(body, dict) and set(body) == {"save_satellite"}:
            # FUT-32: override what a satellite can do, in Settings -> Household -> Satellites.
            from declan.ha import satellites
            target = body["save_satellite"] if isinstance(body["save_satellite"], dict) else {}
            try:
                saved = satellites.save(target.get("entity_id"),
                                        {key: value for key, value in target.items() if key != "entity_id"})
                handler.send_json(200, {"saved": True, "overrides": saved})
            except ValueError as error:
                handler.send_json(400, {"error": str(error)})
            except OSError:
                handler.send_json(503, {"error": "Could not save that."})
            return
        if isinstance(body, dict) and set(body) == {"save_house_info"}:
            # #834 P2: the car's name and battery sensor (FUT-31) in Settings -> Household.
            from declan.ha import house_info
            try:
                handler.send_json(200, {"saved": True, "house_info": house_info.save(body["save_house_info"])})
            except ValueError as error:
                handler.send_json(400, {"error": str(error)})
            except OSError:
                handler.send_json(503, {"error": "Could not save that."})
            return
        if isinstance(body, dict) and len(body) == 1 and set(body) <= {"save_theme", "theme_satellite", "try_theme"}:
            # FUT-46: entrance themes in Settings -> Household.
            from declan.ha import entrance_themes
            value = next(iter(body.values()))
            try:
                if "save_theme" in body:
                    value = value if isinstance(value, dict) else {}
                    handler.send_json(200, {"saved": True, "theme": entrance_themes.save_theme(
                        value.get("person"), value.get("media_id"), value.get("enabled"))})
                elif "theme_satellite" in body:
                    handler.send_json(200, {"saved": True, "satellite": entrance_themes.save_satellite(value)})
                else:
                    from urllib.request import ProxyHandler, build_opener
                    from declan.timers import timers
                    opener = build_opener(ProxyHandler({}))
                    entrance_themes.try_theme(
                        value, lambda api, data=None: timers.ha_json(opener, api, data=data, timeout=7))
                    handler.send_json(200, {"played": True})
            except ValueError as error:
                handler.send_json(400, {"error": str(error)})
            except (OSError, sqlite3.Error):
                handler.send_json(503, {"error": "Could not change the entrance themes."})
            return
        if isinstance(body, dict) and len(body) == 1 and set(body) <= {"save_usual", "forget_usual"}:
            # FUT-44: add, change or forget "the usual" for a room in Settings -> Household.
            from declan.turn import usual
            target = next(iter(body.values()))
            target = target if isinstance(target, dict) else {}
            try:
                if "save_usual" in body:
                    steps = usual.save(target.get("room"), target.get("window"), target.get("steps"))
                    handler.send_json(200, {"saved": True, "steps": steps})
                else:
                    handler.send_json(200, {"forgotten": usual.forget(target.get("room"), target.get("window"))})
            except ValueError as error:
                handler.send_json(400, {"error": str(error)})
            except (OSError, sqlite3.Error):
                handler.send_json(503, {"error": "Could not change the usual."})
            return
        if not isinstance(body, dict) or set(body) != {"settings"}:
            handler.send_json(400, {"error": "Send household settings."})
            return
        try:
            handler.send_json(200, household_settings.save(body["settings"]))
        except ValueError as error:
            handler.send_json(400, {"error": str(error)})
        except OSError:
            handler.send_json(503, {"error": "Could not save the household settings."})
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
