"""HTTP handler adapter functions with live server dependencies."""

def send_body(handler, status, data, content_type, filename=None, *, r):
    http_response_transport = r.http_response_transport
    DECLAN_EVENT_LOG = r.DECLAN_EVENT_LOG

    return http_response_transport.send_body(
        handler, status, data, content_type, filename=filename, logger=DECLAN_EVENT_LOG,
    )

def send_json(handler, status, data, *, r):
    http_response_transport = r.http_response_transport
    DECLAN_EVENT_LOG = r.DECLAN_EVENT_LOG

    return http_response_transport.send_json(
        handler, status, data, logger=DECLAN_EVENT_LOG,
    )

def spotify_settings(handler, body=None, *, r):
    media_settings_routes = r.media_settings_routes
    music = r.music

    return media_settings_routes.spotify_settings(handler, body, music=music)

def has_ingress_access(handler, *, r):
    http_ingress_security = r.http_ingress_security

    return http_ingress_security.has_ingress_access(handler)

def approved_player_settings(handler, body=None, *, r):
    media_settings_routes = r.media_settings_routes
    ha_device_connection = r.ha_device_connection
    ha_inventory = r.ha_inventory
    read_music_inventory_result = r.read_music_inventory_result
    read_ha_areas = r.read_ha_areas
    approved_area_labels = r.approved_area_labels
    approved_media_players = r.approved_media_players

    return media_settings_routes.approved_player_settings(
        handler, body, ha_device_connection=ha_device_connection,
        ha_inventory=ha_inventory,
        read_music_inventory_result=read_music_inventory_result,
        read_ha_areas=read_ha_areas, approved_area_labels=approved_area_labels,
        approved_media_players=approved_media_players,
    )

def do_GET(handler, *, r):
    music = r.music
    ha_device_connection = r.ha_device_connection
    get_request_dispatch = r.get_request_dispatch
    os = r.os
    health_readiness = r.health_readiness
    home_assistant_status_result = r.home_assistant_status_result
    RELEASE_VERSION = r.RELEASE_VERSION
    configuration = r.configuration
    script_discovery = r.script_discovery
    command_responses = r.command_responses
    history = r.history
    declan_logs = r.declan_logs
    diagnostics = r.diagnostics
    updates = r.updates
    voicepipeline = r.voicepipeline
    voice_profiles = r.voice_profiles
    ai_budget = r.ai_budget
    ai_settings = r.ai_settings
    ai_credentials = r.ai_credentials
    spotify_playlists = r.spotify_playlists

    return get_request_dispatch.dispatch(
        handler, assist_token=os.environ.get("DECLAN_ASSIST_TOKEN", ""),
        ingress=handler.has_ingress_access(),
        logo_path=r.Path(r.__file__).with_name("logo.png"),
        health_readiness=health_readiness,
        ha_status=home_assistant_status_result,
        release_version=RELEASE_VERSION, music=music,
        configuration=configuration, script_discovery=script_discovery,
        ha_connection=ha_device_connection, command_responses=command_responses,
        history=history, logs=declan_logs, diagnostics=diagnostics,
        updates=updates, voicepipeline=voicepipeline,
        voice_profiles=voice_profiles, ai_budget=ai_budget,
        ai_settings=ai_settings, ai_credentials=ai_credentials,
        spotify_playlists=spotify_playlists,
    )

def transcribe_browser_audio(handler, *, r):
    DECLAN_EVENT_LOG = r.DECLAN_EVENT_LOG
    ha_device_connection = r.ha_device_connection
    os = r.os
    configuration = r.configuration
    speech_http_routes = r.speech_http_routes
    web_stt = r.web_stt
    traced_transcribe_result = r.traced_transcribe_result

    return speech_http_routes.transcribe_browser_audio(
        handler, web_stt=web_stt, connection_factory=ha_device_connection,
        transcribe=traced_transcribe_result,
        token=os.environ.get("DECLAN_HA_TOKEN", "").strip(),
        pipeline=configuration.get("DECLAN_WEB_ASSIST_PIPELINE", "").strip(),
        logger=DECLAN_EVENT_LOG,
    )

