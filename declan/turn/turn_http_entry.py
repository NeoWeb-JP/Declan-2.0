"""Orchestrate an HTTP conversation turn using the per-request TurnServices."""

from declan.http import post_ingress_orchestration
from declan.turn import turn_dispatch_orchestration
from declan.turn import turn_response_completion
from declan.turn import turn_session_preflight
def handle_post(handler, *, services):
    prepared = post_ingress_orchestration.prepare(handler, services=services)
    if prepared is None:
        return
    body, message, session_id = prepared
    turn = turn_session_preflight.prepare(
        handler, body, message, session_id, services=services,
    )
    if turn is None:
        return
    session_id, phrase, effective_message = turn.session_id, turn.phrase, turn.effective_message
    pending_retry = turn.pending_retry
    source, scope, origin_device, satellite = turn.source, turn.scope, turn.origin_device, turn.satellite
    last_lights, last_device, last_information = turn.last_lights, turn.last_device, turn.last_information
    action_results = services.ActionEvidenceBuffer()
    dispatch_result = turn_dispatch_orchestration.dispatch(
        phrase, source=source, origin_device=origin_device,
        satellite=satellite, action_results=action_results,
        scope=scope, last_lights=last_lights,
        last_device=last_device, last_information=last_information,
        services=services,
    )
    response = turn_response_completion.complete(
        handler, body=body, message=message, effective_message=effective_message,
        session_id=session_id, phrase=phrase, source=source, scope=scope,
        pending_retry=pending_retry, action_results=action_results,
        dispatch_result=dispatch_result, services=services,
    )
    handler.send_json(200, response.to_wire())

