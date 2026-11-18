"""Bounded conversation session state and chat fallback orchestration.

Callers serialize access to the injected session store. No server globals are imported.
"""
from datetime import datetime
from time import monotonic
import secrets
from chat_recall_privacy import safe_chat_text

def _prune_expired_sessions(sessions, now, idle_seconds):
    """Expire all idle sessions, including entries whose access order changed."""
    for key, state in list(sessions.items()):
        if not isinstance(state, dict) or not isinstance(state.get("at"), (int, float)) or now - state["at"] >= idle_seconds:
            sessions.pop(key, None)


def _store_session(sessions, session_id, state, *, limit=128):
    """Keep active sessions bounded with oldest-access eviction."""
    sessions[session_id] = state
    sessions.move_to_end(session_id)
    while len(sessions) > limit:
        sessions.popitem(last=False)


def _safe_session_name(state):
    """Sanitise legacy/injected session names before any spoken reply."""
    name = safe_chat_text(state.get("name"))
    state["name"] = name[:40] if name is not None else None
    return state["name"]


def _remember_safe_chat(state, message, *, routine_reply):
    """Only retain harmless chat in the bounded spoken-recall history."""
    messages = [safe for item in state.get("recent_messages", [])
                if (safe := safe_chat_text(item)) is not None]
    safe_message = safe_chat_text(message)
    if safe_message is not None and routine_reply is None:
        messages.append(safe_message)
    state["recent_messages"] = messages[-3:]


def _compose_chat_reply(state, *, kind, name, routine_reply, guest_mode, decorate,
                        unmatched_reply, recall, session_id):
    """Select a chat reply and return updated state without managing its lifetime."""
    if routine_reply is not None:
        reply = routine_reply
    elif name:
        proposed_name = name[1].strip()
        safe_name = safe_chat_text(proposed_name)
        if safe_name is None:
            reply = "I cannot remember that as a name."
        else:
            state["name"] = safe_name[:40]
            reply = decorate(f"Nice to meet you, {state['name']}.", "greeting", guest_mode)
    elif kind == "recall_name":
        safe_name = _safe_session_name(state)
        reply = f"Your name is {safe_name}." if safe_name else "I don't know your name yet."
        if safe_name:
            reply = decorate(reply, "memory", guest_mode)
    elif kind == "recall_message":
        safe_last = safe_chat_text(state.get("last"))
        reply = f"You said: {safe_last}" if safe_last else "I don\'t have a safe earlier message to repeat."
        if safe_last:
            reply = decorate(reply, "memory", guest_mode)
    elif kind == "recall_earlier":
        history = [safe for item in state.get("recent_messages", [])
                   if (safe := safe_chat_text(item)) is not None][-3:]
        reply = ("Earlier you said: " + " | ".join(history)) if history else "I don't have earlier messages to recall."
        if history:
            reply = decorate(reply, "memory", guest_mode)
    elif kind == "forget_chat":
        if recall is not None:
            recall.forget(session_id)
        state = {"last": None, "name": None, "recent_messages": []}
        reply = "I have cleared this conversation's short-term memory."
    elif kind == "time":
        reply = decorate(f"It's {datetime.now().astimezone():%H:%M} here.", "time", guest_mode)
    elif kind == "greeting":
        safe_name = _safe_session_name(state)
        reply = f"Hello, {safe_name}." if safe_name else "Hello. I'm Declan."
        reply = decorate(reply, "greeting", guest_mode)
    else:
        reply = unmatched_reply
    return state, reply


def _finalize_chat_session(state, *, message, kind, routine_reply, lighting_context,
                           scope, recall, session_id, sessions, now):
    """Apply the winning reply outcome to chat retention and action context."""
    is_forget = kind == "forget_chat" and routine_reply is None
    if not is_forget:
        # Never turn a private command or credential-bearing utterance into
        # a repeatable, 30-minute spoken chat memory.
        _remember_safe_chat(state, message, routine_reply=routine_reply)
    state.update(last=None if is_forget else message, at=now)
    if recall is not None and not is_forget and routine_reply is None:
        recall.remember(session_id, state, now)
    if not is_forget and lighting_context is not None:
        state["lighting_context"] = lighting_context
        state["lighting_scope"] = scope
    _store_session(sessions, session_id, state)
    return state


def _load_chat_session(sessions, recall, session_id, now):
    """Accept only opaque string IDs; never trust arbitrary client values as keys."""
    if not isinstance(session_id, str) or not session_id or len(session_id) > 256:
        session_id = None
    state = sessions.pop(session_id, None) if session_id is not None else None
    if not isinstance(state, dict):
        state = None
    if state is None and recall is not None and session_id is not None:
        # Chat-only recall must never restore expired action context.
        state = recall.restore(session_id, now)
        if not isinstance(state, dict):
            state = None
    if state is None:
        session_id = secrets.token_urlsafe(24)
        state = {"last": None, "name": None, "recent_messages": []}
    return session_id, state


def converse(message, session_id, routine_reply=None, *, lighting_context=None, scope=None, guest_mode=None,
             sessions, idle_seconds, name_pattern, chat_commands, unmatched_reply, decorate, recall=None):
    if not isinstance(message, str):
        raise ValueError("chat message must be a string")
    now = monotonic()
    _prune_expired_sessions(sessions, now, idle_seconds)
    session_id, state = _load_chat_session(sessions, recall, session_id, now)
    command = message.casefold().strip(" .?!")
    name = name_pattern.fullmatch(message.strip(" .?!"))
    kind = chat_commands.get(command)
    state, reply = _compose_chat_reply(
        state, kind=kind, name=name, routine_reply=routine_reply,
        guest_mode=guest_mode, decorate=decorate, unmatched_reply=unmatched_reply,
        recall=recall, session_id=session_id)
    _finalize_chat_session(
        state, message=message, kind=kind, routine_reply=routine_reply,
        lighting_context=lighting_context, scope=scope, recall=recall,
        session_id=session_id, sessions=sessions, now=now)
    return {"session_id": session_id, "reply": reply}


