"""Training, retired routine mapping, and history mutation POST routes."""
from declan.http import native_training_post
from declan.http import history_intents_post
from declan.http import history_post_routes

ROUTES = frozenset({
    "/api/native/routine-responses", "/api/native/routines",
    "/api/native/intents", "/api/history/intents", "/api/history/clear",
})


def handles(path):
    return path in ROUTES


def dispatch(handler, body, *, command_responses, routine_responses,
             discover, connection, history, voicepipeline, unmatched_reply,
             forget_intent, edit_intent, teach_intent, storage_errors):
    path = handler.path
    if path == "/api/native/routine-responses":
        native_training_post.handle_routine_responses(
            handler, body, command_responses=command_responses,
            routine_responses=routine_responses,
            discover=discover, connection=connection,
        )
    elif path == "/api/native/routines":
        handler.send_json(
            410, {"error": "Routine mappings are retired. Manage scripts in Home Assistant."},
        )
    elif path == "/api/native/intents":
        native_training_post.handle_native_intents(
            handler, body, history=history, voicepipeline=voicepipeline,
            unmatched_reply=unmatched_reply,
        )
    elif path == "/api/history/intents":
        history_intents_post.handle_history_intents(
            handler, body, forget_intent=forget_intent,
            edit_intent=edit_intent, teach_intent=teach_intent,
            unmatched_reply=unmatched_reply,
        )
    elif path == "/api/history/clear":
        history_post_routes.handle_history_clear(
            handler, body, clear=history.clear, storage_errors=storage_errors,
        )
    else:
        raise ValueError("Unsupported training/history POST route")
