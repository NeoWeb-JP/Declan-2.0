"""Typed runtime dispatch boundaries with live server dependency injection."""

def run_routine_result(period, *, action_results=None, movie_action=None, movie_room="lounge", movie_app=None, approved=False, r):
    return r.routine_execution_dispatch.run_routine_result(
        period, action_results=action_results, movie_action=movie_action,
        movie_room=movie_room, movie_app=movie_app, approved=approved,
        gates=r.ROUTINE_EXECUTION_GATES, connect=r.ha_device_connection,
        registry=r.routine_registry, cooldown=r.ROUTINE_COOLDOWN,
        token_hex=r.secrets.token_hex, request_factory=r.Request, tracker=r.track_routine,
        completion=r.routine_completion_result, launch_app=r.launch_movie_app_result,
        evidence_factory=r.MovieActionEvidence, append_evidence=r.append_action_evidence,
        sleep_fn=r.sleep,
    )


def routine_completion_result(result, request_id, routine_id, period, movie_action, action_results, *, r):
    return r.routine_execution_dispatch.routine_completion_result(
        result, request_id, routine_id, period, movie_action, action_results,
        parse_steps=r.routine_action_results_typed, extend_evidence=r.extend_action_evidence,
        sass=r.add_sass,
    )


def handle_light_request(phrase, *, action_results=None, last_lights=(), origin_device=None, r):
    """Compatibility entry point; parsing and correction flow live outside HTTP."""
    return r.lighting_intents.handle_light_request(
        phrase, parse_light_command=r.parse_light_command, set_lights=r.set_lights,
        action_results=action_results, last_lights=last_lights, origin_device=origin_device)


def handle_light_request_result(phrase, *, action_results=None, last_lights=(), origin_device=None, r):
    """Keep typed lighting outcomes through intent and execution dispatch."""
    return r.lighting_intents.handle_light_request_result(
        phrase, parse_light_command=r.parse_light_command, set_lights=r.set_lights_result,
        action_results=action_results, last_lights=last_lights, origin_device=origin_device)


def run_sexy_time_result(operation, connection, *, approved=False, r):
    return r.bedroom_routine_dispatch.run_sexy_time_result(
        operation, connection, approved=approved, registry=r.routine_registry,
        gates=r.ROUTINE_EXECUTION_GATES, inventory_reader=r.read_music_inventory_result,
        inventory_module=r.ha_inventory, music_provider=r.music, request_factory=r.Request,
        token_hex=r.secrets.token_hex, choose_response=r.choose_line, guest_mode=r.read_guest_mode,
    )


def start_dinner_result(connection, *, approved=False, r):
    return r.household_routine_dispatch.start_dinner_result(
        connection, approved=approved, policy=r.personality_policy,
        registry=r.routine_registry, choose_response=r.choose_line,
        guest_mode=r.read_guest_mode, request_factory=r.Request,
    )


def guest_assignment_result(operation, connection, *, r):
    return r.household_routine_dispatch.guest_assignment_result(
        operation, connection, entities=r.household_entities,
        sass=r.add_sass, request_factory=r.Request,
    )


def render_web_voice(message, *, r):
    return r.ha_speech_transport.render_web_voice(
        message, connect=r.ha_device_connection, config=r.configuration,
        request_factory=r.Request,
    )


def set_lights_result(name, desired_state, *, brightness=None, preview=False, require_all=False, relative_step=10,
               action_results=None, origin_device=None, r):
    return r.lighting_execution_dispatch.set_lights_result(
        name, desired_state, brightness=brightness, preview=preview,
        require_all=require_all, relative_step=relative_step,
        action_results=action_results, origin_device=origin_device,
        connect=r.ha_device_connection, inventory_reader=r.read_ha_inventory_result,
        inventory_module=r.ha_inventory, entities=r.household_entities,
        sass=r.add_sass, areas_reader=r.read_ha_areas,
        switch_dispatch=r.set_switch_as_light_result, intents=r.lighting_intents,
        evidence_factory=r.LightingActionEvidence, append_evidence=r.append_action_evidence,
        clock=r.monotonic, sleeper=r.sleep, request_factory=r.Request,
    )


def guarded_openai_fallback_result(message, *, source, exposed_entities=(), r):
    return r.ai_fallback_dispatch.guarded_openai_fallback_result(
        message, source=source, exposed_entities=exposed_entities,
        settings_reader=r.ai_settings.read, intent_gate=r.ai_intent_gate.is_action_request,
        connect=r.ha_device_connection, inventory_reader=r.read_ha_inventory_result,
        inventory_module=r.ha_inventory, context_selector=r.ai_context.select,
        planner_module=r.openai_planner, settings_module=r.ai_settings,
        history_module=r.history, fallback_runner=r.guarded_fallback.run_guarded_result,
        dispatcher=r.ha_dispatcher.dispatch_result, pricing=r.ai_pricing.charge,
        bounded_plan=r._bounded_ai_plan, evidence_factory=r.FallbackActionEvidence,
        response_factory=r.guarded_fallback_dispatch.FallbackResponse,
        location_reader=r.ha_inventory.read_locations,
    )

