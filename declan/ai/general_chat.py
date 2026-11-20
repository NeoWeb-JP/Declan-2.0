"""Conversation settings and the bounded, budgeted OpenAI call used by the agent.

D4 (#802) made general chat opt-in and separately bounded. The conversation
agent (declan/ai/conversation_agent.py) now covers chat, help and loose
device requests, and uses this module for:
- settings: on/off and a monthly conversation budget (.data/general-chat.json,
  kept for compatibility with the chat setting it replaces);
- spend: every call reserves the AI per-request ceiling in the main AI ledger
  (so the AI monthly budget still caps everything) and is also counted in the
  conversation slice (chat_budget). Rejected requests cost 0; unknown failures
  keep the reservation.
"""
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from declan.ai import ai_budget, ai_credentials, ai_pricing, ai_settings
from declan.ai.model_response_results import ModelResponseResult, ModelResponseStatus
from declan.core import history

LOGGER = logging.getLogger(__name__)
PATH = Path(__file__).resolve().parents[2] / ".data" / "general-chat.json"
DEFAULTS = {"enabled": False, "monthly_budget_usd": "20.00"}
TIMEOUT_SECONDS = 10
_LOCK = Lock()


class ModelUnavailable(ValueError):
    """No model reply: settings, key, budget or request problem. Caller falls back."""


def _money(value):
    return ai_settings._money(value, allow_zero=True)


def validate(payload):
    if not isinstance(payload, dict) or set(payload) != set(DEFAULTS):
        raise ValueError("Send enabled and monthly_budget_usd.")
    if type(payload["enabled"]) is not bool:
        raise ValueError("Conversation must be on or off.")
    _money(payload["monthly_budget_usd"])
    return dict(payload)


def read(path=None):
    path = PATH if path is None else path
    try:
        return validate(json.loads(Path(path).read_text(encoding="utf-8")))
    except (FileNotFoundError, ValueError, OSError, TypeError):
        return dict(DEFAULTS)


def save(payload, path=None):
    settings = validate(payload)
    path = Path(PATH if path is None else path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(settings, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return settings


def enabled(path=None):
    return read(path)["enabled"]


def _month(now=None):
    now = now or datetime.now(timezone.utc)
    return now.astimezone(timezone.utc).strftime("%Y-%m")


def month_spent(db, now=None):
    db.execute("CREATE TABLE IF NOT EXISTS chat_budget (month TEXT PRIMARY KEY, spent INTEGER NOT NULL)")
    row = db.execute("SELECT spent FROM chat_budget WHERE month = ?", (_month(now),)).fetchone()
    return row[0] if row else 0


def _add_spend(db, amount, now=None):
    with db:
        db.execute("CREATE TABLE IF NOT EXISTS chat_budget (month TEXT PRIMARY KEY, spent INTEGER NOT NULL)")
        db.execute("INSERT INTO chat_budget VALUES (?, ?) ON CONFLICT(month) DO UPDATE SET spent = spent + ?",
                   (_month(now), amount, amount))


def model_config(*, ai_settings_reader=None, key_reader=None):
    """Model, pricing profile, key and limits from AI settings, or ModelUnavailable."""
    try:
        ai = (ai_settings_reader or ai_settings.read)()
        profile = ai_pricing.model_profile(ai["model"], ai.get("model_config"))
        ai_pricing.require_available(profile)
        key = (key_reader or ai_credentials.get_key)()
    except (OSError, ValueError, sqlite3.Error, KeyError, TypeError):
        raise ModelUnavailable("AI model or key is not configured") from None
    if not isinstance(key, str) or not key.strip():
        raise ModelUnavailable("OpenAI API key is not configured")
    return {"model": ai["model"], "profile": profile, "key": key,
            "monthly": _money(ai["monthly_budget_usd"]),
            "ceiling": ai_settings._money(ai["request_ceiling_usd"], allow_zero=False)}


def _send(body, *, key, opener):
    data = json.dumps(body).encode("utf-8")
    request = Request("https://api.openai.com/v1/responses", data=data, method="POST",
                      headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    opener = opener or build_opener(ProxyHandler({}))
    deadline = monotonic() + TIMEOUT_SECONDS
    with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        raw = response.read(262145)
    if monotonic() >= deadline or len(raw) > 262144:
        raise ValueError("Late or oversized model response")
    return json.loads(raw)


def call(body, *, config, settings=None, opener=None, database=None, now=None, usage=None):
    """Send one Responses request within both budgets; return the output text.

    Raises ModelUnavailable when it cannot or did not get a usable reply. When
    a request was sent, ``usage`` (a dict, if given) receives the settled
    charge in micro-USD and the round-trip time in milliseconds.
    """
    settings = settings or read()
    if not settings["enabled"]:
        raise ModelUnavailable("Conversation is off")
    input_rate, output_rate = ai_pricing.rate_pair(config["model"], config["profile"])
    worst = (len(json.dumps(body).encode("utf-8")) * input_rate
             + body.get("max_output_tokens", 0) * output_rate + 999999) // 1000000
    ceiling = config["ceiling"]
    if worst > ceiling:
        raise ModelUnavailable("Request would exceed the per-request ceiling")
    slice_limit = _money(settings["monthly_budget_usd"])
    with _LOCK, (database or history.database)() as db:
        if month_spent(db, now) + ceiling > slice_limit or ceiling > config["monthly"]:
            raise ModelUnavailable("Monthly conversation budget reached")
        try:
            reservation = ai_budget.reserve(db, limit_micro_usd=config["monthly"],
                                            max_request_micro_usd=ceiling, now=now)
        except ai_budget.BudgetExhausted:
            raise ModelUnavailable("Monthly AI budget reached") from None
        charged, text, failure = ceiling, None, None
        started = monotonic()
        try:
            result = _send(body, key=config["key"], opener=opener)
            try:
                charged = min(ceiling, ai_pricing.charge(config["model"], result.get("usage"),
                                                         profile=config["profile"]))
            except (ValueError, TypeError, AttributeError):
                charged = ceiling
            parsed = ModelResponseResult.parse(result)
            if parsed.status is ModelResponseStatus.COMPLETED and parsed.text:
                text = parsed.text
            else:
                failure = "incomplete"
        except HTTPError as error:
            error.close()
            if error.code in {400, 401, 403, 404, 413, 415, 422, 429}:
                charged = 0  # Rejected before any model work.
            failure = f"HTTP {error.code}"
        except (OSError, URLError, ValueError, TypeError, KeyError, AttributeError) as error:
            failure = type(error).__name__
        if usage is not None:
            usage.update(charged=charged, duration_ms=round((monotonic() - started) * 1000))
        try:
            ai_budget.settle(db, reservation, charged)
            _add_spend(db, charged, now)
        except (ValueError, sqlite3.Error):
            LOGGER.warning("Conversation spend could not be settled; reservation retained")
    if text is None:
        LOGGER.warning("Conversation model request failed (%s)", failure)
        raise ModelUnavailable("No usable model reply")
    return text


def listing(path=None, database=None):
    """Settings plus this month's conversation spend in micro-USD, for the panel."""
    settings = read(path)
    try:
        with (database or history.database)() as db:
            spent = month_spent(db)
    except (OSError, sqlite3.Error):
        spent = None
    return {"settings": settings, "month_spent_micro_usd": spent}


LOG_KINDS = frozenset({"act", "ask", "answer", "failed"})
LOG_DAYS = 35


def log_turn(kind, *, charged, duration_ms, general, database=None, now=None):
    """Record one agent turn for the Understanding card (no text, no names)."""
    if kind not in LOG_KINDS:
        return
    stamp = (now or datetime.now(timezone.utc)).timestamp()
    try:
        with (database or history.database)() as db:
            db.execute("CREATE TABLE IF NOT EXISTS conversation_log (created_at REAL NOT NULL, kind TEXT NOT NULL, "
                       "spent INTEGER NOT NULL, duration_ms INTEGER NOT NULL, general INTEGER NOT NULL)")
            db.execute("DELETE FROM conversation_log WHERE created_at < ?", (stamp - LOG_DAYS * 86400,))
            db.execute("INSERT INTO conversation_log VALUES (?, ?, ?, ?, ?)",
                       (stamp, kind, int(charged or 0), int(duration_ms or 0), 1 if general else 0))
    except (OSError, sqlite3.Error):
        LOGGER.warning("Could not record the conversation turn")


def week_summary(db, *, now):
    """Agent turns, kinds, spend and typical time over the seven days before ``now`` (epoch)."""
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversation_log'").fetchone()
    rows = db.execute("SELECT kind, spent, duration_ms, general FROM conversation_log WHERE created_at BETWEEN ? AND ?",
                      (now - 7 * 86400, now)).fetchall() if exists else []
    kinds = {kind: sum(1 for row in rows if row[0] == kind) for kind in sorted(LOG_KINDS)}
    durations = sorted(row[2] for row in rows if row[0] != "failed")
    return {"turns": len(rows), **kinds, "general_questions": sum(1 for row in rows if row[3]),
            "spent_micro_usd": sum(row[1] for row in rows),
            "median_ms": durations[len(durations) // 2] if durations else None}
