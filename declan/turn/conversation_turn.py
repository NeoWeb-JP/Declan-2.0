"""Run the conversation agent for a turn the local parsers could not handle.

Order (owner decision, 20 Nov): exact commands stay local and instant. When
local dispatch has no reply, could not resolve its target, or the request was
too vague to act on ("play something"), and Conversation is on, the agent
decides to act, ask or answer. Device actions run through the guarded,
verified executor; Declan commands are re-checked and run through the normal
dispatch, after the same sensitive-routine confirmation gate as spoken
commands. If the agent is off or unavailable, the turn continues exactly as
before (AI planner, then the rephrase prompt).
"""
from __future__ import annotations

import json
import logging
import sqlite3
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from declan.ai import conversation_agent, general_chat
from declan.core import diagnostics
from declan.core.execution_results import Outcome

LOGGER = logging.getLogger(__name__)
DIALOGUE_SECONDS = 300
MAX_SESSIONS = 200
VAGUE_MUSIC = frozenset({
    "something", "anything", "some music", "music", "some tunes", "tunes", "a song", "some songs",
    "songs", "something good", "something nice", "whatever", "something chill", "something relaxing",
})
_DIALOGUES: OrderedDict[str, dict] = OrderedDict()
_DIALOGUE_LOCK = Lock()


@dataclass(frozen=True)
class AgentTurn:
    dispatch_result: object
    follow_up: bool = False
    immediate_reply: dict | None = None  # A confirmation prompt: send it as-is.


def _key(session_id, scope):
    return f"{session_id}|{scope or ''}"


def dialogue(session_id, scope, *, now=None):
    now = monotonic() if now is None else now
    with _DIALOGUE_LOCK:
        entry = _DIALOGUES.get(_key(session_id, scope))
        if not entry or now - entry["at"] > DIALOGUE_SECONDS:
            return []
        return list(entry["turns"])


def awaiting_answer(session_id, scope=None, *, now=None):
    """True when Declan's last line in this session was a question (#373 gate bypass)."""
    now = monotonic() if now is None else now
    with _DIALOGUE_LOCK:
        for key, entry in _DIALOGUES.items():
            if (key.split("|", 1)[0] == session_id and (scope is None or key == _key(session_id, scope))
                    and entry.get("asked") and now - entry["at"] <= DIALOGUE_SECONDS):
                return True
    return False


def remember(session_id, scope, person, declan, *, asked, now=None):
    if not isinstance(session_id, str) or not session_id:
        return
    now = monotonic() if now is None else now
    key = _key(session_id, scope)
    with _DIALOGUE_LOCK:
        entry = _DIALOGUES.pop(key, None)
        turns = entry["turns"] if entry and now - entry["at"] <= DIALOGUE_SECONDS else []
        turns = (turns + [{"who": "person", "text": person}, {"who": "declan", "text": declan}])
        _DIALOGUES[key] = {"turns": turns[-conversation_agent.MAX_DIALOGUE:], "at": now, "asked": asked}
        while len(_DIALOGUES) > MAX_SESSIONS:
            _DIALOGUES.popitem(last=False)


def prefers_agent(phrase, *, parse_music):
    """Requests the local parser would take too literally ("play something")."""
    try:
        parsed = parse_music(phrase)
    except (ValueError, TypeError):
        return False
    return bool(parsed) and isinstance(parsed[1], str) and parsed[1] in VAGUE_MUSIC


def needs_agent(dispatch_result):
    if dispatch_result is None:
        return True
    return dispatch_result.reply is None or dispatch_result.outcome is Outcome.UNRESOLVED


def _routine_names(scripts, phrases):
    names = set()
    for item in scripts:
        try:
            aliases = sorted(phrases(item), key=lambda alias: (len(alias), alias))
        except (KeyError, TypeError, AttributeError):
            continue
        for alias in aliases:
            if not alias.startswith(("what is", "give me")):
                names.add(alias)
                break
    return names


def gather(*, connection, inventory_rows, exposed, origin_device, read_areas, music_rooms,
           scripts, phrases, allowed_domains):
    """Context for the agent from trusted HA data. Only exposed entities can be acted on."""
    origin = None
    if origin_device and connection is not None:
        try:
            areas = read_areas(connection, origin_device)
            origin = next(iter(areas), None) if isinstance(areas, dict) else None
        except (OSError, ValueError, TypeError):
            origin = None
    exposed = set(exposed or ())
    domains = (set(allowed_domains) | {"media_player"}) & conversation_agent.AGENT_DOMAINS
    devices = [row for row in inventory_rows
               if isinstance(row, dict) and row.get("entity_id") in exposed
               and row["entity_id"].split(".", 1)[0] in domains]
    rooms = {row.get("declan_area") for row in inventory_rows
             if isinstance(row, dict) and isinstance(row.get("declan_area"), str)}
    if origin:
        rooms.add(origin)
    return {"you_are_in": origin, "devices": devices, "areas": rooms,
            "music_rooms": set(music_rooms) | {"everywhere", "upstairs", "downstairs"},
            "routines": _routine_names(scripts, phrases)}


def decide(message, context, *, session_id, scope, checks, settings=None, config=None,
           opener=None, database=None):
    """Ask the model; return a validated AgentDecision and the permitted entity map."""
    payload, permitted = conversation_agent.build_context(
        message, you_are_in=context["you_are_in"], dialogue=dialogue(session_id, scope),
        devices=context["devices"], areas=context["areas"], music_rooms=context["music_rooms"],
        routines=context["routines"])
    config = config or general_chat.model_config()
    body = conversation_agent.request_body(payload, permitted, model=config["model"],
                                           profile=config["profile"])
    general = not payload["devices"] and not payload["routines"] and not payload["conversation"]
    usage: dict = {}
    started = monotonic()

    def log(kind):
        if usage:  # Only turns that actually reached the model are logged.
            general_chat.log_turn(kind, charged=usage.get("charged"), duration_ms=usage.get("duration_ms"),
                                  general=general, database=database)
            diagnostics.record("conversation_agent", started, kind=kind, general=general,
                               model_ms=usage.get("duration_ms"), spent_micro_usd=usage.get("charged"),
                               devices=len(payload["devices"]))
    try:
        text = general_chat.call(body, config=config, settings=settings, opener=opener, database=database,
                                 usage=usage)
        raw = json.loads(text)
        decision = conversation_agent.parse_decision(raw, permitted, routines=context["routines"], checks=checks)
    except (general_chat.ModelUnavailable, ValueError, TypeError, KeyError):
        log("failed")
        raise
    log(decision.kind)
    if decision.rejected:
        LOGGER.info("Conversation agent: %d proposal(s) rejected by validation", len(decision.rejected))
    return decision, permitted


def execute(decision, permitted, *, connection, dispatch_command, confirm_command,
            run_devices, result_factory):
    """Carry out an act decision. Returns AgentTurn.

    run_devices(actions, permitted, connection) -> ExecutionResult (verified).
    dispatch_command(phrase) -> DispatchResult. confirm_command(phrase) -> reply
    dict for a sensitive routine that needs a spoken "yes", otherwise None.
    """
    if decision.kind != "act":
        outcome = Outcome.UNRESOLVED if decision.kind == "ask" else Outcome.CHAT_ANSWER
        return AgentTurn(result_factory(decision.say, outcome), follow_up=decision.kind == "ask")
    replies, outcomes, results = [], [], []
    if decision.device_actions:
        if connection is None:
            replies.append("Home Assistant is unavailable, so I couldn't change the devices.")
            outcomes.append(Outcome.UNAVAILABLE)
        else:
            try:
                summary = run_devices(decision.device_actions, permitted, connection)
            except (ValueError, OSError, sqlite3.Error):
                summary = None
            if summary is None:
                replies.append("I couldn't safely change those devices.")
                outcomes.append(Outcome.FAILED)
            elif summary.outcome is Outcome.CONFIRMED:
                replies.append(decision.say or "Done.")
                outcomes.append(Outcome.CONFIRMED)
            else:
                replies.append(summary.reply)
                outcomes.append(summary.outcome)
    for command in decision.commands:
        prompt = confirm_command(command)
        if prompt is not None:
            return AgentTurn(None, immediate_reply=prompt)
        result = dispatch_command(command)
        results.append(result)
        if result is not None and result.reply:
            replies.append(result.reply)
            outcomes.append(result.outcome)
        else:
            replies.append(f"I couldn't do '{command}'.")
            outcomes.append(Outcome.UNRESOLVED)
    reply = " ".join(part.strip() for part in replies if part and part.strip())
    outcome = _combined(outcomes)
    base = next((result for result in results if result is not None), None)
    return AgentTurn(result_factory(reply, outcome, base=base))


def _combined(outcomes):
    outcomes = [outcome for outcome in outcomes if outcome is not None]
    if not outcomes:
        return Outcome.UNRESOLVED
    if all(outcome is outcomes[0] for outcome in outcomes):
        return outcomes[0]
    good = {Outcome.CONFIRMED, Outcome.REPORTED_SUCCESS, Outcome.EXECUTION_COMPLETED, Outcome.REQUESTED,
            Outcome.STARTED, Outcome.TIMER_SET}
    return Outcome.PARTIAL if any(outcome in good for outcome in outcomes) else outcomes[0]
