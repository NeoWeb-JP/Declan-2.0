"""POST ingress authorization, payload validation and operational routing."""


def prepare(handler, *, r):
    if not r.post_entry_gates.enforce(
        handler, assist_token=r.os.environ.get("DECLAN_ASSIST_TOKEN", ""),
        ingress=handler.has_ingress_access(),
        authenticate_assist=r.assist_auth_http.authenticate_assist,
        enforce_known_route=r.post_route_gate_http.enforce_known_route,
        enforce_origin=r.post_origin_auth_http.enforce_access,
        transcribe=handler.transcribe_browser_audio,
    ):
        return
    try:
        # Assist-token callers may review or resolve pending matches, but not
        # perform destructive VoicePipeline management operations.
        authorized, body = r.post_payload_validation.read_authorized_body(
            handler, ingress=handler.has_ingress_access(),
        )
        if not authorized:
            return
        if r.post_body_routing.dispatch(
            handler, body, spotify_save=handler.spotify_settings,
            ai_replace_key=r.ai_credentials.replace_key,
            ai_save=r.ai_settings.save, ai_configured=r.ai_credentials.configured,
            r.music=r.music, r.spotify_playlists=r.spotify_playlists,
            playlist_handler=r.music_playlists_post.handle_music_playlists,
            opener_factory=lambda: r.build_opener(r.ProxyHandler({})),
            voice_manage=r.voicepipeline.manage,
            pipeline_error=r.voicepipeline.PipelineError,
            profiles_manage=r.voice_profiles.manage,
            preview=r.configuration.preview, apply=r.configuration.apply,
            r.command_responses=r.command_responses,
            r.routine_responses=r.routine_responses,
            discover=r.script_discovery.discover_result,
            connection=r.ha_device_connection, r.history=r.history,
            r.voicepipeline=r.voicepipeline, unmatched_reply=r.UNMATCHED_REPLY,
            forget_intent=r.history.forget_intent,
            edit_intent=r.history.edit_intent,
            teach_intent=r.history.teach_intent,
            storage_errors=(OSError, r.sqlite3.Error),
        ):
            return
        if r.post_operational_routing.dispatch_before_validation(
            handler, body, r.updates=r.updates, release_version=r.RELEASE_VERSION,
        ):
            return
        message, session_id = r.post_payload_validation.message_and_session(body)
    except (ValueError, TypeError, KeyError, AttributeError):
        r.post_payload_validation.send_validation_error(self)
        return
    if r.post_operational_routing.dispatch_after_validation(
        handler, body, message=message, session_id=session_id,
        render=r.render_web_voice, record=r.history.record,
        token_urlsafe=r.secrets.token_urlsafe,
        action_results=r.routine_action_results_typed,
    ):
        return
    return body, message, session_id
