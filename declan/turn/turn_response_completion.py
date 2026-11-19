"""Prepare and atomically finalize voice-turn responses using live server hooks."""


def complete(handler, *, body, message, effective_message, session_id, phrase,
             source, scope, pending_retry, action_results, dispatch_result, r):
    turn_response_preparation = r.turn_response_preparation
    os = r.os
    fallback_entity_authorization = r.fallback_entity_authorization
    guarded_fallback_dispatch = r.guarded_fallback_dispatch
    guarded_openai_fallback_result = r.guarded_openai_fallback_result
    read_guest_mode = r.read_guest_mode
    read_visitors_present = r.read_visitors_present
    personality_policy = r.personality_policy
    CHAT_COMMANDS = r.CHAT_COMMANDS
    turn_atomic_finalization = r.turn_atomic_finalization
    SESSION_STORE = r.SESSION_STORE
    monotonic = r.monotonic
    turn_context_preparation = r.turn_context_preparation
    turn_finalization = r.turn_finalization
    turn_response_composition = r.turn_response_composition
    turn_response_orchestration = r.turn_response_orchestration
    music = r.music
    routine_responses = r.routine_responses
    lighting_intents = r.lighting_intents
    parse_light_command = r.parse_light_command
    command_responses = r.command_responses
    response_composition = r.response_composition
    turn_persistence_orchestration = r.turn_persistence_orchestration
    UNMATCHED_REPLY = r.UNMATCHED_REPLY
    retry_learning = r.retry_learning
    history = r.history
    diagnostics = r.diagnostics
    session_turn_state = r.session_turn_state
    retry_training_persistence = r.retry_training_persistence
    conversation_persistence = r.conversation_persistence
    converse = r.converse
    routine_reply, outcome = dispatch_result.reply, dispatch_result.outcome
    routine_status, routine_turn = dispatch_result.routine_status, dispatch_result.routine_turn
    routine_voice_result = dispatch_result.routine_voice_result
    lighting_context, information_context = dispatch_result.lighting_context, dispatch_result.information_context
    status_target, light_result = dispatch_result.status_target, dispatch_result.light_result
    response_preparation = turn_response_preparation.prepare(
        effective_message, routine_reply=routine_reply, outcome=outcome,
        light_result=light_result, body=body,
        authorization=handler.headers.get("Authorization", ""),
        bridge_token=os.environ.get("DECLAN_ASSIST_TOKEN", ""),
        source=source, action_results=action_results,
        exposed_entities=fallback_entity_authorization.exposed_entities,
        dispatch_fallback=guarded_fallback_dispatch.dispatch_fallback_result,
        fallback_handler=guarded_openai_fallback_result,
        guest_mode_reader=read_guest_mode,
        visitors_reader=read_visitors_present,
        personality_policy=personality_policy,
        chat_commands=CHAT_COMMANDS,
        information_context=information_context,
    )
    routine_reply, outcome = response_preparation.reply, response_preparation.outcome
    guest_mode = response_preparation.guest_mode
    visitor_present = response_preparation.visitor_present
    response_guest_mode = response_preparation.response_guest_mode
    information_context = response_preparation.information_context
    response = turn_atomic_finalization.finalize(
        session_id, action_results, light_result, outcome, scope, message, effective_message, routine_reply, lighting_context, response_guest_mode, routine_turn, phrase, guest_mode, visitor_present, routine_voice_result, routine_status, status_target, information_context, pending_retry, source, body,
        sessions=SESSION_STORE.sessions, session_lock=SESSION_STORE.lock, clock=monotonic,
        turn_context_preparation=turn_context_preparation,
        turn_finalization=turn_finalization,
        turn_response_composition=turn_response_composition,
        turn_response_orchestration=turn_response_orchestration,
        personality_policy=personality_policy,
        personality_lines=__import__("declan.turn.personality", fromlist=["LINES"]).LINES,
        music=music, routine_responses=routine_responses,
        lighting_intents=lighting_intents, parse_light_command=parse_light_command,
        command_responses=command_responses,
        response_composition=response_composition,
        turn_persistence_orchestration=turn_persistence_orchestration,
        unmatched_reply=UNMATCHED_REPLY, retry_learning=retry_learning,
        history=history, diagnostics=diagnostics,
        session_turn_state=session_turn_state,
        retry_training_persistence=retry_training_persistence,
        conversation_persistence=conversation_persistence,
        log_error=handler.log_error, converse=converse,
    )
    return response
