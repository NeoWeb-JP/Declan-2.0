"""Conversation history GET routes behind the existing server authentication gates."""
import json
import sqlite3
from urllib.parse import parse_qs, urlsplit


def handles(path):
    return (path == "/api/history/export"
            or path == "/api/history/quality"
            or path.startswith("/api/history/recording-links?")
            or path == "/api/history"
            or path.startswith("/api/history?"))


def dispatch(handler, *, history):
    path = handler.path
    if path == "/api/history/export":
        try:
            turns = history.recent(limit=None)
        except (OSError, sqlite3.Error):
            handler.send_json(503, {"error": "Conversation history is unavailable."})
            return
        handler.send_body(
            200, json.dumps({"turns": list(reversed(turns))}, ensure_ascii=False).encode("utf-8"),
            "application/json", "declan-conversation-history.json",
        )
    elif path == "/api/history/quality":
        from declan.core import understanding_quality
        from declan.turn.command_vocabulary import UNMATCHED_REPLY
        from declan.voice import speaker_settings
        try:
            handler.send_json(200, understanding_quality.summary(
                unmatched_reply=UNMATCHED_REPLY,
                speaker_threshold=speaker_settings.threshold(),
            ))
        except (OSError, sqlite3.Error, ValueError):
            handler.send_json(503, {"error": "Understanding summary is unavailable."})
    elif path.startswith("/api/history/recording-links?"):
        try:
            params = parse_qs(urlsplit(path).query)
            if set(params) != {"ids"} or len(params["ids"]) != 1:
                raise ValueError("Missing recording identifiers.")
            identifiers = params["ids"][0].split(",")
            links = history.verified_recording_turns(identifiers)
            linked = set(links.values())
            turns = {str(row["id"]): row for row in history.recent(limit=None)
                     if row["id"] in linked}
            handler.send_json(200, {"links": links, "turns": turns})
        except ValueError:
            handler.send_json(400, {"error": "Invalid recording identifiers."})
        except (OSError, sqlite3.Error):
            handler.send_json(503, {"error": "Recording links unavailable."})
    elif path == "/api/history" or path.startswith("/api/history?"):
        try:
            params = parse_qs(urlsplit(path).query)
            before = int(params["before"][0]) if "before" in params else None
            if before is not None and not 0 < before < 2**63:
                raise ValueError
            turns = history.recent(before, limit=51)
            aliases = history.learned_intents() if before is None else None
            for turn in turns:
                turn["teachable"] = (
                    turn["source"] in {"assist", "browser_voice", "browser_keyboard", "ha_sentence"}
                    and 0 < len(history.normalize_phrase(turn["message"])) <= 120
                )
        except ValueError:
            handler.send_json(400, {"error": "Invalid history cursor."})
            return
        except (OSError, sqlite3.Error):
            handler.send_json(503, {"error": "Conversation history is unavailable."})
            return
        handler.send_json(200, {
            "turns": turns[:50], "next": turns[49]["id"] if len(turns) > 50 else None,
            "learned_intents": aliases,
        })
    else:
        raise ValueError("Unsupported history read route")
