"""Native training and response-management POST orchestration."""

import sqlite3


def handle_routine_responses(handler, body, *, command_responses, routine_responses,
                             discover, connection):
    try:
        if not isinstance(body, dict) or set(body) not in (
                {"entity_id"}, {"entity_id", "profile", "expected"}):
            raise ValueError("Invalid response change")
        entity = body.get("entity_id")
        if isinstance(entity, str) and entity.startswith("command:"):
            item = command_responses.item(entity)
            manager = command_responses
        else:
            if not isinstance(entity, str) or not routine_responses.ENTITY.fullmatch(entity):
                raise ValueError("Select a routine or command")
            discovery = discover(connection(), fresh=True)
            if discovery.error is not None:
                handler.send_json(503, {
                    "error": "Home Assistant routines unavailable. Try again.",
                })
                return
            item = next((row for row in discovery.scripts if row["entity_id"] == entity), None)
            if item is None:
                raise ValueError("That routine is no longer available. Reload routines.")
            manager = routine_responses
        result = (manager.save(item, body["profile"], body["expected"])
                  if "profile" in body else manager.snapshot(item))
        handler.send_json(200, result)
    except ValueError as error:
        handler.send_json(400, {"error": str(error)})
    except (OSError, sqlite3.Error):
        handler.send_json(503, {"error": "Routine responses unavailable."})


def handle_native_intents(handler, body, *, history, voicepipeline, unmatched_reply):
    try:
        if not isinstance(body, dict):
            raise ValueError("Invalid intention change.")
        if set(body) == {"phrase", "target", "previous"}:
            history.edit_intent(body["phrase"], body["target"], body["previous"])
        elif set(body) == {"forget", "previous"}:
            phrase = body["forget"]
            if (not isinstance(phrase, str) or not isinstance(body["previous"], str)
                    or history.learned_intent(phrase) != body["previous"]):
                raise ValueError("Intention changed. Refresh before forgetting.")
            history.forget_intent(phrase)
        elif set(body) == {"recording_id", "target"}:
            recording_id = voicepipeline.identifier(body["recording_id"])
            rows = voicepipeline.interactions() + voicepipeline.interactions(history=True)
            matches = [row for row in rows if row.get("id") == recording_id]
            transcripts = {row.get("transcript") for row in matches}
            if (len(transcripts) != 1 or not matches or any(
                    voicepipeline.InteractionReviewResult.parse(row.get("status")).blocks_teaching
                    for row in matches)):
                raise ValueError("Refresh and choose a recording with a transcript.")
            history.teach_phrase(transcripts.pop(), body["target"])
        elif set(body) == {"turn_id", "target"} and type(body["turn_id"]) is int:
            history.teach_intent(body["turn_id"], body["target"], unmatched_reply)
        else:
            raise ValueError("Invalid intention change.")
        handler.send_json(200, {"saved": True})
    except ValueError as error:
        handler.send_json(400, {"error": str(error)})
    except voicepipeline.PipelineError as error:
        handler.send_json(error.status, {"error": str(error)})
    except (OSError, sqlite3.Error):
        handler.send_json(503, {"error": "Intention change unavailable."})
