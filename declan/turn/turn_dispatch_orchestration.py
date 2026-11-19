"""Orchestrate preview, direct, routine and fallback dispatch for a voice turn.

Server-owned collaborators arrive as a `TurnServices` container built per request,
so server-level patches and configuration still take effect.
"""

from declan.core import conditions
from declan.ha import device_status
from declan.ha import lighting_command_dispatch
from declan.ha import lighting_context_finalization
from declan.ha import lighting_intents
from declan.music import music
from declan.timers import timer_command_dispatch
from declan.timers import timers
from declan.turn import command_registry
from declan.turn import guest_assignment_command
from declan.turn import personality_policy
from declan.turn import roast
from declan.turn import roast_command_dispatch
from declan.turn import routine_follow_on
from declan.turn import routine_preview_detection
from declan.turn import routine_preview_dispatch
from declan.turn import turn_direct_dispatch
from declan.turn import turn_fallback_dispatch
from declan.turn import turn_preview_stage
from declan.turn import turn_routine_stage
from dataclasses import dataclass
from declan.core.execution_results import Outcome


@dataclass(frozen=True)
class DispatchResult:
    reply: str | None
    outcome: Outcome | None
    routine_status: str | None
    routine_turn: object
    routine_voice_result: object
    lighting_context: object
    information_context: object
    status_target: object
    light_result: object

    def __post_init__(self):
        if self.reply is not None and not isinstance(self.reply, str):
            raise ValueError("Dispatch reply must be text or None")
        if self.outcome is not None:
            object.__setattr__(self, "outcome", Outcome(self.outcome))
        if self.routine_status is not None and not isinstance(self.routine_status, str):
            raise ValueError("Routine status must be text or None")


def dispatch(phrase, *, source, origin_device, satellite, action_results,
             scope, last_lights, last_device, last_information, services):
    build_opener = services.build_opener
    ProxyHandler = services.ProxyHandler
    NoRedirect = services.NoRedirect
    preview_routine_result = services.preview_routine_result
    read_guest_mode = services.read_guest_mode
    add_sass = services.add_sass
    stop_pending_routines_result = services.stop_pending_routines_result
    stop_everywhere_result = services.stop_everywhere_result
    ha_device_connection = services.ha_device_connection
    read_visitors_present = services.read_visitors_present
    GUEST_COMMANDS = services.GUEST_COMMANDS
    guest_assignment_result = services.guest_assignment_result
    select_routine_turn_result = services.select_routine_turn_result
    execute_routine_result = services.execute_routine_result
    read_music_inventory_result = services.read_music_inventory_result
    handle_light_request_result = services.handle_light_request_result
    chained_outcome_result = services.chained_outcome_result
    read_ha_inventory_result = services.read_ha_inventory_result
    configured_guest_mode_entity = services.configured_guest_mode_entity
    read_ha_areas = services.read_ha_areas
    search_media_result = services.search_media_result
    parse_light_command = services.parse_light_command
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
