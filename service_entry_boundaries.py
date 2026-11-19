"""Typed service entrypoints using the live server compatibility surface."""


def run_custom_routine_result(name, action_results=None, *, approved=False, parameters=None, r):
    return r.routine_execution_dispatch.run_custom_routine_result(
        name, action_results=action_results, approved=approved, parameters=parameters,
        registry=r.routine_registry, connect=r.ha_device_connection, areas_reader=r.read_ha_areas,
        token_hex=r.secrets.token_hex, request_factory=r.Request, tracker=r.track_routine,
        parse_steps=r.routine_action_results_typed, extend_evidence=r.extend_action_evidence,
    )


def search_media_result(phrase, *, r):
    return r.media_title_search.search_media_result(
        phrase, config=r.configuration, connect=r.ha_device_connection,
        agents=r.media_search_agents, request_factory=r.Request,
    )


def launch_movie_app_result(connection, remote, app, *, r):
    return r.movie_ha_helpers.launch_movie_app_result(
        connection, remote, app, request_factory=r.Request,
    )


def discover_movie_entities(connection, room, *, script, remote, needs_remote, r):
    return r.movie_ha_helpers.discover_movie_entities(
        connection, room, script=script, remote=remote, needs_remote=needs_remote,
        inventory_reader=r.read_ha_inventory_result, area_reader=r.read_ha_areas,
        inventory_module=r.ha_inventory,
    )


def verify_legacy_lounge_start(connection, script, *, r):
    return r.movie_ha_helpers.verify_legacy_lounge_start(
        connection, script, inventory_reader=r.read_ha_inventory_result,
        inventory_module=r.ha_inventory, entities=r.household_entities,
    )


def ha_device_connection(*, r):
    return r.ha_speech_transport.ha_device_connection(
        environ=r.os.environ, redirect_handler=r.NoRedirect,
        proxy_handler=r.ProxyHandler, opener_factory=r.build_opener,
    )


def converse(message, session_id, routine_reply=None, *, lighting_context=None, scope=None, guest_mode=None, r):
    """Caller holds the session store lock."""
    return r.session_orchestration.converse(
        message, session_id, routine_reply, lighting_context=lighting_context,
        scope=scope, guest_mode=guest_mode, sessions=r.SESSION_STORE.sessions,
        idle_seconds=r.IDLE_SECONDS, name_pattern=r.NAME_PATTERN,
        chat_commands=r.CHAT_COMMANDS, unmatched_reply=r.UNMATCHED_REPLY,
        decorate=r.add_sass, recall=r.SESSION_STORE.chat_recall,
    )
