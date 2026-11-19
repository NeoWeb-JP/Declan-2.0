"""Pre-conversation POST routes for settings and training history."""

import settings_voice_post
import training_history_post


def dispatch(handler, body, *, spotify_save, ai_replace_key, ai_save,
             ai_configured, music, spotify_playlists, playlist_handler,
             opener_factory, voice_manage, pipeline_error, profiles_manage,
             preview, apply, command_responses, routine_responses,
             discover, connection, history, voicepipeline, unmatched_reply,
             forget_intent, edit_intent, teach_intent, storage_errors):
    """Return True only when a settings or training route handled the request."""
    if settings_voice_post.handles(handler.path):
        settings_voice_post.dispatch(
            handler, body, spotify_save=spotify_save,
            ai_replace_key=ai_replace_key, ai_save=ai_save,
            ai_configured=ai_configured, music=music,
            spotify_playlists=spotify_playlists,
            playlist_handler=playlist_handler,
            opener_factory=opener_factory,
            voice_manage=voice_manage, pipeline_error=pipeline_error,
            profiles_manage=profiles_manage, preview=preview, apply=apply,
        )
        return True
    if training_history_post.handles(handler.path):
        training_history_post.dispatch(
            handler, body, command_responses=command_responses,
            routine_responses=routine_responses, discover=discover,
            connection=connection, history=history,
            voicepipeline=voicepipeline, unmatched_reply=unmatched_reply,
            forget_intent=forget_intent, edit_intent=edit_intent,
            teach_intent=teach_intent, storage_errors=storage_errors,
        )
        return True
    return False
