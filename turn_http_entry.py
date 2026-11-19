"""Orchestrate an HTTP conversation turn using live server dependencies."""

def handle_post(handler, *, r):
    prepared = r.post_ingress_orchestration.prepare(handler, r=r)
    if prepared is None:
        return
    body, message, session_id = prepared
    turn = r.turn_session_preflight.prepare(
        handler, body, message, session_id, r=r,
    )
    if turn is None:
        return
    session_id, phrase, effective_message = turn.session_id, turn.phrase, turn.effective_message
    pending_retry = turn.pending_retry
    source, scope, origin_device, satellite = turn.source, turn.scope, turn.origin_device, turn.satellite
    last_lights, last_device, last_information = turn.last_lights, turn.last_device, turn.last_information
    action_results = r.ActionEvidenceBuffer()
    dispatch_result = r.turn_dispatch_orchestration.dispatch(
        phrase, source=source, origin_device=origin_device,
        satellite=satellite, action_results=action_results,
        scope=scope, last_lights=last_lights,
        last_device=last_device, last_information=last_information,
        r=r,
    )
    response = r.turn_response_completion.complete(
        handler, body=body, message=message, effective_message=effective_message,
        session_id=session_id, phrase=phrase, source=source, scope=scope,
        pending_retry=pending_retry, action_results=action_results,
        dispatch_result=dispatch_result, r=r,
    )
    handler.send_json(200, response.to_wire())

