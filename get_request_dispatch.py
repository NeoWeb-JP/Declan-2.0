"""Authenticated GET route orchestration, separate from the HTTP handler."""

from pathlib import Path

import get_access_gate_http
import history_read_routes
import native_read_routes
import operational_read_routes
import settings_read_routes
import system_read_routes


def dispatch(handler, *, assist_token, ingress, logo_path, health_readiness,
             ha_status, release_version, music, configuration, script_discovery,
             ha_connection, command_responses, history, logs, diagnostics,
             updates, voicepipeline, voice_profiles, ai_budget, ai_settings,
             ai_credentials, spotify_playlists):
    if not get_access_gate_http.enforce_access(
        handler, ingress=ingress, token=assist_token,
    ):
        return
        if system_read_routes.handles(handler.path):
            system_read_routes.dispatch(
                handler, logo_path=logo_path,
                health_readiness=health_readiness,
                ha_status=ha_status,
                release_version=release_version,
            )
        elif native_read_routes.handles(handler.path):
            native_read_routes.dispatch(
                handler, music=music, configuration=configuration,
                script_discovery=script_discovery, ha_connection=ha_connection,
                command_responses=command_responses, history=history,
                logs=logs, diagnostics=diagnostics,
            )
        elif operational_read_routes.handles(handler.path):
            operational_read_routes.dispatch(
                handler, ha_status=ha_status,
                release_version=release_version, updates=updates,
                configuration=configuration,
            )
        elif settings_read_routes.handles(handler.path):
            settings_read_routes.dispatch(
                handler, voicepipeline=voicepipeline, voice_profiles=voice_profiles,
                diagnostics=diagnostics, history=history, ai_budget=ai_budget,
                ai_settings=ai_settings, ai_credentials=ai_credentials,
                spotify_playlists=spotify_playlists,
            )
        elif history_read_routes.handles(handler.path):
            history_read_routes.dispatch(handler, history=history)
        else:
            handler.send_json(404, {"error": "Not found."})