"""Information, device and lighting dispatch with strict precedence."""
from dataclasses import dataclass

import information_command_dispatch
import information_result_response
import device_command_dispatch
import device_result_response
import lighting_result_dispatch


@dataclass(frozen=True)
class FallbackDispatchResult:
    reply: object = None
    outcome: object = None
    information_context: object = None
    status_target: object = None
    lighting_context: object = None
    light_result: object = None


def dispatch(phrase, source, opener, last_information, last_device,
             origin_device, satellite, action_results, last_lights, scope,
             lighting_context, *, command_registry, conditions, add_sass,
             read_guest_mode, device_status, ha_device_connection,
             read_ha_inventory_result, GUEST_MODE_ENTITY, music,
             read_music_inventory_result, read_ha_areas, search_media_result,
             lighting_intents, parse_light_command, handle_light_request_result,
             lighting_command_dispatch, lighting_context_finalization):
    routine_reply = outcome = information_context = status_target = light_result = None
    information_dispatch = information_command_dispatch.dispatch_information(
        phrase, source=source,
        registry_factory=command_registry.information_registry,
        context_factory=command_registry.RequestContext,
        matches=conditions.matches, follow_up=conditions.follow_up,
        handle=conditions.handle_result,
        question_context=conditions.question_context,
        opener=opener, last_information=last_information,
        decorate=add_sass, guest_mode=read_guest_mode,
    )
    if information_dispatch:
        information_response = information_result_response.information_response(information_dispatch)
        routine_reply, outcome = (
            information_response.result.reply, information_response.result.outcome
        )
        information_context = information_response.information_context
    else:
        device_dispatch = device_command_dispatch.dispatch_device(
            phrase, source=source, last_device=last_device,
            origin_device=origin_device, satellite=satellite,
            registry_factory=command_registry.registry,
            dependencies_factory=command_registry.Dependencies,
            context_factory=command_registry.RequestContext,
            parse_status=device_status.parse,
            describe_status=device_status.describe_result,
            connection=ha_device_connection, inventory=read_ha_inventory_result,
            decorate=add_sass, guest_mode_entity=GUEST_MODE_ENTITY,
            parse_feedback=music.parse_feedback, feedback=music.feedback_result,
            parse_control=music.parse_control, control=music.control_result,
            parse_music=music.parse, play=music.play_result,
            music_inventory=read_music_inventory_result, areas=read_ha_areas,
            search_media=search_media_result,
        )
        if device_dispatch is not None:
            device_response = device_result_response.device_response(device_dispatch)
            routine_reply, outcome = (
                device_response.result.reply, device_response.result.outcome
            )
            status_target = device_response.status_target
        else:
            lighting_result = lighting_result_dispatch.dispatch_lighting_response(
                phrase, source=source, origin_device=origin_device,
                satellite=satellite,
                registry_factory=command_registry.lighting_registry,
                context_factory=command_registry.RequestContext,
                matches=lighting_intents.matches,
                parse_light_command=parse_light_command,
                handle_light_request=handle_light_request_result,
                action_results=action_results, last_lights=last_lights,
                scope=scope,
                dispatch_lighting=lighting_command_dispatch.dispatch_lighting,
                confirmed_lighting_context=(
                    lighting_context_finalization.confirmed_lighting_context
                ),
            )
            if lighting_result is not None:
                routine_reply, outcome = lighting_result.result.reply, lighting_result.result.outcome
                lighting_context = lighting_result.lighting_context
                light_result = lighting_result.result

    if routine_reply is None and outcome is None:
        return None
    return FallbackDispatchResult(
        reply=routine_reply, outcome=outcome,
        information_context=information_context, status_target=status_target,
        lighting_context=lighting_context, light_result=light_result,
    )
