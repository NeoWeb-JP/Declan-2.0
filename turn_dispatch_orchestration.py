"""Orchestrate preview, direct, routine and fallback dispatch for a voice turn.

Dependencies are resolved from the live server module at invocation time to retain
server-level test monkeypatches and integration configuration.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DispatchResult:
    reply: object
    outcome: object
    routine_status: object
    routine_turn: object
    routine_voice_result: object
    lighting_context: object
    information_context: object
    status_target: object
    light_result: object


def dispatch(phrase, *, source, origin_device, satellite, action_results,
             scope, last_lights, last_device, last_information, r):
    build_opener = r.build_opener
    ProxyHandler = r.ProxyHandler
    NoRedirect = r.NoRedirect
    turn_preview_stage = r.turn_preview_stage
    routine_preview_dispatch = r.routine_preview_dispatch
    routine_preview_detection = r.routine_preview_detection
    preview_routine_result = r.preview_routine_result
    timer_command_dispatch = r.timer_command_dispatch
    command_registry = r.command_registry
    timers = r.timers
    read_guest_mode = r.read_guest_mode
    add_sass = r.add_sass
    turn_direct_dispatch = r.turn_direct_dispatch
    stop_pending_routines_result = r.stop_pending_routines_result
    stop_everywhere_result = r.stop_everywhere_result
    ha_device_connection = r.ha_device_connection
    roast = r.roast
    roast_command_dispatch = r.roast_command_dispatch
    read_visitors_present = r.read_visitors_present
    personality_policy = r.personality_policy
    guest_assignment_command = r.guest_assignment_command
    GUEST_COMMANDS = r.GUEST_COMMANDS
    guest_assignment_result = r.guest_assignment_result
    turn_routine_stage = r.turn_routine_stage
    select_routine_turn_result = r.select_routine_turn_result
    execute_routine_result = r.execute_routine_result
    routine_follow_on = r.routine_follow_on
    music = r.music
    read_music_inventory_result = r.read_music_inventory_result
    handle_light_request_result = r.handle_light_request_result
    chained_outcome_result = r.chained_outcome_result
    turn_fallback_dispatch = r.turn_fallback_dispatch
    conditions = r.conditions
    device_status = r.device_status
    read_ha_inventory_result = r.read_ha_inventory_result
    configured_guest_mode_entity = r.configured_guest_mode_entity
    read_ha_areas = r.read_ha_areas
    search_media_result = r.search_media_result
    lighting_intents = r.lighting_intents
    parse_light_command = r.parse_light_command
    lighting_command_dispatch = r.lighting_command_dispatch
    lighting_context_finalization = r.lighting_context_finalization
    routine_reply = outcome = routine_status = None
    routine_turn = routine_voice_result = None
    light_result = lighting_context = status_target = information_context = None
    opener = build_opener(ProxyHandler({}), NoRedirect())
    early_result = turn_preview_stage.resolve(
        phrase, source=source, origin_device=origin_device,
        satellite=satellite, opener=opener,
        preview_dispatch=routine_preview_dispatch.dispatch_preview_result,
        detect_phrase=routine_preview_detection.routine_preview_phrase,
        preview_routine=preview_routine_result,
        timer_dispatch=timer_command_dispatch.dispatch_timer,
        registry_factory=command_registry.timer_registry,
        context_factory=command_registry.RequestContext,
        matches=timers.matches, handle=timers.handle_result,
        guest_mode=read_guest_mode, decorate=add_sass,
    )
    routine_turn = None
    routine_voice_result = None
    if early_result is not None:
        routine_reply, outcome = early_result.reply, early_result.outcome
    elif direct_result := turn_direct_dispatch.dispatch(
        phrase, source=source, origin_device=origin_device,
        satellite=satellite,
        stop_registry=command_registry.stop_registry,
        context_factory=command_registry.RequestContext,
        stop_routines=stop_pending_routines_result,
        stop_everywhere=stop_everywhere_result,
        connection=ha_device_connection,
        roast_target=roast.target,
        respond_to_roast=roast_command_dispatch.respond_to_roast_result,
        guest_mode=read_guest_mode, visitors_present=read_visitors_present,
        response_guest_mode=personality_policy.response_guest_mode,
        roast_respond=roast.respond,
        assignment_action=guest_assignment_command.assignment_action,
        guest_commands=GUEST_COMMANDS,
        guest_assignment=guest_assignment_result,
    ):
        routine_reply, outcome = direct_result.reply, direct_result.outcome
        routine_status = direct_result.routine_status
    elif routine_result := turn_routine_stage.dispatch(
        phrase, source=source, origin_device=origin_device,
        satellite=satellite, action_results=action_results,
        scope=scope, last_lights=last_lights,
        registry_factory=command_registry.routine_registry,
        context_factory=command_registry.RequestContext,
        select=select_routine_turn_result, execute=execute_routine_result,
        follow_on_execute=routine_follow_on.execute_result,
        parse_music=music.parse, play_music=music.play_result,
        connection=ha_device_connection,
        music_inventory=read_music_inventory_result,
        handle_lighting=handle_light_request_result,
        chained_outcome=chained_outcome_result,
    ):
        routine_status = routine_result.routine_status
        routine_turn = routine_result.routine_turn
        routine_reply, outcome = routine_result.reply, routine_result.outcome
        lighting_context = routine_result.lighting_context
        routine_voice_result = routine_result.routine_voice_result
    else:
        fallback_dispatch = turn_fallback_dispatch.dispatch(
            phrase, source, opener, last_information, last_device, origin_device, satellite, action_results, last_lights, scope, lighting_context,
            command_registry=command_registry,
            conditions=conditions,
            add_sass=add_sass,
            read_guest_mode=read_guest_mode,
            device_status=device_status,
            ha_device_connection=ha_device_connection,
            read_ha_inventory_result=read_ha_inventory_result,
            GUEST_MODE_ENTITY=configured_guest_mode_entity(),
            music=music,
            read_music_inventory_result=read_music_inventory_result,
            read_ha_areas=read_ha_areas,
            search_media_result=search_media_result,
            lighting_intents=lighting_intents,
            parse_light_command=parse_light_command,
            handle_light_request_result=handle_light_request_result,
            lighting_command_dispatch=lighting_command_dispatch,
            lighting_context_finalization=lighting_context_finalization,
        )
        if fallback_dispatch is not None:
            routine_reply, outcome = fallback_dispatch.reply, fallback_dispatch.outcome
            information_context = fallback_dispatch.information_context
            status_target = fallback_dispatch.status_target
            lighting_context = fallback_dispatch.lighting_context
            light_result = fallback_dispatch.light_result
    return DispatchResult(routine_reply, outcome, routine_status, routine_turn,
                          routine_voice_result, lighting_context, information_context,
                          status_target, light_result)
