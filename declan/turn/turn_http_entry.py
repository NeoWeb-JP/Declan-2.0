"""Orchestrate an HTTP conversation turn using the per-request TurnServices."""
import logging
import sqlite3

from declan.http import post_ingress_orchestration
from declan.turn import (
    conversation_turn,
    local_help,
    turn_dispatch_orchestration,
    turn_response_completion,
    turn_session_preflight,
)

LOGGER = logging.getLogger(__name__)


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

    def dispatch(command_phrase):
        return turn_dispatch_orchestration.dispatch(
            command_phrase, source=source, origin_device=origin_device,
            satellite=satellite, action_results=action_results,
            scope=scope, last_lights=last_lights,
            last_device=last_device, last_information=last_information,
            services=services,
        )

    from declan.ai import general_chat
    from declan.music import music
    agent_on = _conversation_enabled(general_chat)
    help_request = local_help.match(effective_message)
    from declan.turn import christmas, whereabouts
    christmas_request = christmas.match(effective_message) if help_request is None else None
    where_request = whereabouts.match(effective_message) if help_request is None and christmas_request is None else None
    from declan.turn import usual
    usual_request = usual.match(effective_message) if help_request is None else None
    from declan.turn import braai
    braai_request = braai.match(effective_message) if help_request is None and usual_request is None else None
    if braai_request is None and (rewritten := braai.how_long(effective_message)):
        phrase = rewritten  # FUT-43: "how long on the chops?" asks the chops timer
    from declan.ha import intercom, todo_lists
    list_request = (todo_lists.match(effective_message)
                    if help_request is None and christmas_request is None and where_request is None else None)
    intercom_request = (intercom.match(effective_message)
                        if help_request is None and christmas_request is None and where_request is None
                        and list_request is None else None)
    from declan.turn import house_questions
    house_request = (house_questions.match(effective_message)
                     if help_request is None and usual_request is None and braai_request is None
                     and christmas_request is None and list_request is None else None)
    if help_request is not None:
        dispatch_result = _local_help(handler, body, help_request, origin_device=origin_device,
                                      satellite=satellite, services=services, conversation_on=agent_on)
    elif usual_request is not None:
        # FUT-44: "the usual" for the room that heard you and the time of day.
        dispatch_result = _usual(usual_request, dispatch, services, origin_device or satellite)
    elif braai_request is not None:
        # FUT-43: braai time = Braai music, garden lights and a rain check, with braai sass.
        from declan.turn import conversation_entry
        reply, outcome = braai.run(braai_request, dispatch)
        dispatch_result = conversation_entry._result_factory(reply, outcome)
    elif christmas_request is not None:
        dispatch_result = _christmas(christmas_request)
    elif list_request is not None:
        # FUT-27: shopping and to-do lists live in Home Assistant's own to-do lists.
        dispatch_result = _todo(list_request, services)
    elif house_request is not None and (house_result := _house_question(
            house_request, services, origin_device or satellite)) is not None:
        # #834 P2: who's home and other household questions, straight from Home Assistant.
        dispatch_result = house_result
    elif intercom_request is not None and (intercom_result := _intercom(
            intercom_request, services, origin_device or satellite)) is not None:
        # FUT-25: "tell the kitchen dinner's ready"; None means it wasn't for a room ("tell me a joke").
        dispatch_result = intercom_result
    elif where_request is not None and where_request[2]:
        # FUT-42: "I put the passports in the safe", "where did I leave my glasses?"
        dispatch_result = _whereabouts(where_request, services)
    else:
        dispatch_result = None
    if dispatch_result is not None:
        pass  # Answered locally and for free.
    elif agent_on and conversation_turn.prefers_agent(phrase, parse_music=music.parse):
        dispatch_result = None  # "play something": let the agent choose, not Spotify's literal search.
    else:
        dispatch_result = dispatch(phrase)
    if (where_request is not None and not where_request[2] and conversation_turn.needs_agent(dispatch_result)):
        # FUT-42: a bare "the key is in the drawer" only once nothing else understood it.
        dispatch_result = _whereabouts(where_request, services) or dispatch_result
    if (help_request is None and not agent_on and conversation_turn.needs_agent(dispatch_result)
            and conversation_turn.needs_conversation(effective_message, services.CHAT_COMMANDS)):
        # The device planner cannot answer "where is Peru?"; say how to turn answers on
        # instead of spending money on a plan that is bound to be refused.
        from declan.core.execution_results import Outcome
        from declan.turn import conversation_entry
        dispatch_result = conversation_entry._result_factory(
            conversation_turn.CONVERSATION_OFF_REPLY, Outcome.UNRESOLVED)
    agent_turn = None
    # Built-in chat answers (the time, "what's my name") are answered locally below;
    # the agent has no clock and would only spend money saying so.
    local_chat = conversation_turn.is_chat_command(effective_message, services.CHAT_COMMANDS)
    if help_request is None and agent_on and not local_chat and conversation_turn.needs_agent(dispatch_result):
        from declan.turn import conversation_entry
        agent_turn = conversation_entry.run(
            handler, body, message=message, session_id=session_id, source=source,
            scope=scope, origin_device=origin_device, satellite=satellite,
            action_results=action_results, dispatch=dispatch, services=services,
            local_result=dispatch_result,
        )
        if agent_turn is not None and agent_turn.immediate_reply is not None:
            handler.send_json(200, agent_turn.immediate_reply)
            return
        if agent_turn is not None:
            dispatch_result = agent_turn.dispatch_result
    if dispatch_result is None:
        dispatch_result = dispatch(phrase)
    dispatch_result = _explain_failure(dispatch_result, services)
    response = turn_response_completion.complete(
        handler, body=body, message=message, effective_message=effective_message,
        session_id=session_id, phrase=phrase, source=source, scope=scope,
        pending_retry=pending_retry, action_results=action_results,
        dispatch_result=dispatch_result, services=services,
    )
    wire = response.to_wire()
    if agent_turn is not None:
        if agent_turn.follow_up:
            # Keep the microphone open for the answer to Declan's question.
            wire["continue_conversation"] = True
            wire["follow_up_timeout"] = 10
        conversation_turn.remember(wire.get("session_id"), scope, message, wire.get("reply") or "",
                                   asked=agent_turn.follow_up)
    handler.send_json(200, wire)


def _conversation_enabled(general_chat):
    try:
        return general_chat.enabled()
    except (OSError, ValueError):
        return False


def _explain_failure(dispatch_result, services):
    """FUT-24: say what is actually down, only after checking it."""
    from declan.core.execution_results import Outcome
    if dispatch_result is None or dispatch_result.outcome not in {Outcome.UNAVAILABLE, Outcome.FAILED}:
        return dispatch_result
    from declan.ha import service_health
    from declan.turn import conversation_entry
    try:
        better = service_health.explain(dispatch_result.reply, services.ha_device_connection())
    except (OSError, ValueError, TypeError, AttributeError):
        better = None
    if not better:
        return dispatch_result
    return conversation_entry._result_factory(better, dispatch_result.outcome, base=dispatch_result)


def _intercom(request, services, origin):
    from declan.ha import intercom
    from declan.turn import conversation_entry
    result = intercom.result(request, services.ha_device_connection(), origin=origin)
    return None if result is None else conversation_entry._result_factory(result.reply, result.outcome)


def _house_question(request, services, origin):
    """#834 P2 household questions; None lets the rest of Declan answer."""
    from declan.turn import conversation_entry, house_questions
    try:
        result = house_questions.result(request, services, origin=origin)
    except (OSError, ValueError, TypeError, KeyError) as error:
        LOGGER.warning("Household question failed (%s)", type(error).__name__)
        return None
    if result is None:
        return None
    from declan.ha import household_language
    return conversation_entry._result_factory(household_language.render(result.reply), result.outcome)


def _todo(request, services):
    from declan.ha import todo_lists
    from declan.turn import conversation_entry
    result = todo_lists.result(request, services.ha_device_connection())
    return conversation_entry._result_factory(result.reply, result.outcome)


def _whereabouts(request, services):
    """FUT-42: where things are, answered locally; None lets the rest of Declan answer."""
    from declan.core.execution_results import Outcome
    from declan.turn import conversation_entry, whereabouts
    try:
        guest = services.read_guest_mode() != "off"
    except (OSError, ValueError, TypeError, AttributeError):
        guest = True  # unknown Guest Mode keeps household whereabouts private
    try:
        reply = whereabouts.answer(request, guest=guest)
    except ValueError as error:
        return conversation_entry._result_factory(str(error), Outcome.UNAVAILABLE)
    except (OSError, sqlite3.Error) as error:
        LOGGER.warning("Whereabouts unavailable (%s)", type(error).__name__)
        return conversation_entry._result_factory("I couldn't check my notes just now.", Outcome.FAILED)
    if reply is None:
        return None
    from declan.ha import household_language
    return conversation_entry._result_factory(household_language.render(reply), Outcome.CHAT_ANSWER)


def _here(services, origin):
    """The Home Assistant area of the satellite or device that heard you, or None."""
    if not origin:
        return None
    try:
        areas = services.read_ha_areas(services.ha_device_connection(), origin)
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as error:
        LOGGER.warning("Could not read the satellite's room (%s)", type(error).__name__)
        return None
    return next(iter(areas), None) if isinstance(areas, dict) else None


def _usual(request, dispatch, services, origin):
    """FUT-44: run, set, ask about or forget the usual for a room."""
    from declan.core.execution_results import Outcome
    from declan.turn import conversation_entry, usual
    here = _here(services, origin)
    try:
        if request[0] == "run":
            reply, outcome = usual.run(here, dispatch)
            return conversation_entry._result_factory(reply, outcome)
        try:
            guest = services.read_guest_mode() != "off"
        except (OSError, ValueError, TypeError, AttributeError):
            guest = True  # unknown Guest Mode can't change the household's usuals
        reply = usual.answer(request, here=here, guest=guest)
    except ValueError as error:
        return conversation_entry._result_factory(str(error), Outcome.UNRESOLVED)
    except (OSError, sqlite3.Error) as error:
        LOGGER.warning("The usual is unavailable (%s)", type(error).__name__)
        return conversation_entry._result_factory("I couldn't check the usual just now.", Outcome.FAILED)
    outcome = Outcome.CONFIRMED if request[0] in {"set", "forget"} and not reply.startswith(
        ("Nice try", "Which room", "There wasn't")) else Outcome.CHAT_ANSWER
    return conversation_entry._result_factory(reply, outcome)


def _christmas(request):
    """FUT-59: Christmas mode, the countdown and the guest Wi-Fi, answered locally."""
    from declan.core.execution_results import Outcome
    from declan.turn import christmas, conversation_entry
    try:
        reply = christmas.answer(request)
    except (OSError, ValueError, TypeError, KeyError) as error:
        LOGGER.warning("Christmas request failed (%s)", type(error).__name__)
        return conversation_entry._result_factory("I couldn't change Christmas mode just now.", Outcome.FAILED)
    from declan.ha import household_language
    outcome = Outcome.CONFIRMED if request[0] == "mode" and request[1] != "status" else Outcome.CHAT_ANSWER
    return conversation_entry._result_factory(household_language.render(reply), outcome)


def _local_help(handler, body, request, *, origin_device, satellite, services, conversation_on):
    from declan.core.execution_results import Outcome
    from declan.turn import conversation_entry
    try:
        _, rows, context = conversation_entry.house_context(
            handler, body, origin_device=origin_device, satellite=satellite, services=services)
        try:
            guest = services.read_guest_mode() != "off"
        except (OSError, ValueError, TypeError, AttributeError):
            guest = False
        reply = local_help.answer(request, rows=rows, context=context, conversation_on=conversation_on,
                                  guest=guest)
    except (OSError, ValueError, TypeError, KeyError) as error:
        LOGGER.warning("Local help failed (%s)", type(error).__name__)
        return None
    return conversation_entry._result_factory(reply, Outcome.CHAT_ANSWER) if reply else None
