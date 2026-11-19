"""Server-owned collaborators for one HTTP turn.

These are the names tests and deployments replace on the server module, so
`server.py` builds this container per request and the turn modules read them
from it instead of reaching back into the server module.
"""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TurnServices:
    ActionEvidenceBuffer: Any
    CAPTURE_ARBITER: Any
    CHAT_COMMANDS: Any
    GUEST_COMMANDS: Any
    IDLE_SECONDS: Any
    NoRedirect: Any
    ProxyHandler: Any
    RELEASE_VERSION: Any
    SENSITIVE_CONFIRMATIONS: Any
    SESSION_STORE: Any
    UNMATCHED_REPLY: Any
    add_sass: Any
    build_opener: Any
    chained_outcome_result: Any
    configured_guest_mode_entity: Any
    converse: Any
    execute_routine_result: Any
    guarded_openai_fallback_result: Any
    guest_assignment_result: Any
    ha_device_connection: Any
    handle_light_request_result: Any
    monotonic: Any
    parse_light_command: Any
    preprocess_speech: Any
    preview_routine_result: Any
    read_guest_mode: Any
    read_ha_areas: Any
    read_ha_inventory_result: Any
    read_music_inventory_result: Any
    read_visitors_present: Any
    render_web_voice: Any
    routine_action_results_typed: Any
    search_media_result: Any
    select_routine_turn_result: Any
    stop_everywhere_result: Any
    stop_pending_routines_result: Any
