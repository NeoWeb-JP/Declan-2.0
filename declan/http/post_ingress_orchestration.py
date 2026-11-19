"""POST ingress authorization, payload validation and operational routing."""

import os
import secrets
import sqlite3
from declan.ai import ai_credentials
from declan.ai import ai_settings
from declan.core import configuration
from declan.core import history
from declan.ha import script_discovery
from declan.http import post_body_routing
from declan.http import post_entry_gates
from declan.http import post_operational_routing
from declan.http import post_origin_auth_http
from declan.http import post_payload_validation
from declan.http import post_route_gate_http
from declan.music import music
from declan.music import music_playlists_post
from declan.music import spotify_playlists
from declan.turn import command_responses
from declan.turn import routine_responses
from declan.updates import updates
from declan.voice import assist_auth_http
from declan.voice import voice_profiles
from declan.voice import voicepipeline
def prepare(handler, *, services):
    if not post_entry_gates.enforce(
        handler, assist_token=os.environ.get("DECLAN_ASSIST_TOKEN", ""),
        ingress=handler.has_ingress_access(),
        authenticate_assist=assist_auth_http.authenticate_assist,
        enforce_known_route=post_route_gate_http.enforce_known_route,
        enforce_origin=post_origin_auth_http.enforce_access,
        transcribe=handler.transcribe_browser_audio,
    ):
        return
    try:
        # Assist-token callers may review or resolve pending matches, but not
        # perform destructive VoicePipeline management operations.
        authorized, body = post_payload_validation.read_authorized_body(
            handler, ingress=handler.has_ingress_access(),
        )
        if not authorized:
            return
        if post_body_routing.dispatch(
            handler, body, spotify_save=handler.spotify_settings,
            ai_replace_key=ai_credentials.replace_key,
            ai_save=ai_settings.save, ai_configured=ai_credentials.configured,
            music=music, spotify_playlists=spotify_playlists,
            playlist_handler=music_playlists_post.handle_music_playlists,
            opener_factory=lambda: services.build_opener(services.ProxyHandler({})),
            voice_manage=voicepipeline.manage,
            pipeline_error=voicepipeline.PipelineError,
            profiles_manage=voice_profiles.manage,
            preview=configuration.preview, apply=configuration.apply,
            command_responses=command_responses,
            routine_responses=routine_responses,
            discover=script_discovery.discover_result,
            connection=services.ha_device_connection, history=history,
            voicepipeline=voicepipeline, unmatched_reply=services.UNMATCHED_REPLY,
            forget_intent=history.forget_intent,
            edit_intent=history.edit_intent,
            teach_intent=history.teach_intent,
            storage_errors=(OSError, sqlite3.Error),
        ):
            return
        if post_operational_routing.dispatch_before_validation(
            handler, body, updates=updates, release_version=services.RELEASE_VERSION,
        ):
            return
        message, session_id = post_payload_validation.message_and_session(body)
    except (ValueError, TypeError, KeyError, AttributeError):
        post_payload_validation.send_validation_error(handler)
        return
    if post_operational_routing.dispatch_after_validation(
        handler, body, message=message, session_id=session_id,
        render=services.render_web_voice, record=history.record,
        token_urlsafe=secrets.token_urlsafe,
        action_results=services.routine_action_results_typed,
    ):
        return
    return body, message, session_id
