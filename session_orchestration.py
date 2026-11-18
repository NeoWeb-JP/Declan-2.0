"""Bounded conversation session state and chat fallback orchestration.

Callers serialize access to the injected session store. No server globals are imported.
"""
from datetime import datetime
from time import monotonic
import secrets

def converse(message, session_id, routine_reply=None, *, lighting_context=None, scope=None, guest_mode=None,
             sessions, idle_seconds, name_pattern, chat_commands, unmatched_reply, decorate, recall=None):
    now = monotonic()
    while sessions and now - next(iter(sessions.values()))["at"] >= idle_seconds:
        sessions.popitem(last=False)
    state = sessions.pop(session_id, None)
    if state is None and recall is not None:
        # Recall harmless chat fields only, never expired action context.
        state = recall.restore(session_id, now)
    if state is None:
        session_id = secrets.token_urlsafe(24)
        state = {"last": None, "name": None, "recent_messages": []}
    command = message.casefold().strip(" .?!")
    name = name_pattern.fullmatch(message.strip(" .?!"))
    kind = chat_commands.get(command)
    if routine_reply is not None:
        reply = routine_reply
    elif name:
        state["name"] = name[1].strip()
        reply = decorate(f"Nice to meet you, {state['name']}.", "greeting", guest_mode)
    elif kind == "recall_name":
        reply = f"Your name is {state['name']}." if state["name"] else "I don't know your name yet."
        if state["name"]:
            reply = decorate(reply, "memory", guest_mode)
    elif kind == "recall_message":
        reply = f"You said: {state['last']}" if state["last"] else "This is your first message."
        if state["last"]:
            reply = decorate(reply, "memory", guest_mode)
    elif kind == "recall_earlier":
        history = state.get("recent_messages", [])
        reply = ("Earlier you said: " + " | ".join(history[-3:])) if history else "I don't have earlier messages to recall."
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
        reply = f"Hello, {state['name']}." if state["name"] else "Hello. I'm Declan."
        reply = decorate(reply, "greeting", guest_mode)
    else:
        reply = unmatched_reply
    if kind != "forget_chat":
        messages = list(state.get("recent_messages", []))
        messages.append(message[:160])
        state["recent_messages"] = messages[-3:]
    state.update(last=None if kind == "forget_chat" else message, at=now)
    if recall is not None and kind != "forget_chat":
        recall.remember(session_id, state, now)
    if kind != "forget_chat" and lighting_context is not None:
        state["lighting_context"] = lighting_context
        state["lighting_scope"] = scope
    sessions[session_id] = state
    if len(sessions) > 128:
        sessions.popitem(last=False)
    return {"session_id": session_id, "reply": reply}


