"""Persisted owner-approved AI settings, separate from secret credentials."""
import json
import re

from declan.core.history import database
from declan.ai.ai_pricing import RATES, model_profile, require_available

DEFAULTS = {
    "enabled": False,
    "model": "gpt-5-mini",
    "monthly_budget_usd": "5.00",
    "request_ceiling_usd": "0.05",
    "max_actions": 3,
    "allowed_domains": ["light", "switch", "fan", "cover"],
    "confirmation": "sensitive",
    "routines": "mapped",
    "ambiguous": "clarify",
    "diagnostics": True,
    "show_proposals": False,
    "model_config": None,
}
DOMAINS = frozenset({"light", "switch", "fan", "cover"})
MODEL = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")


def _money(value, *, allow_zero):
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]{0,3})(?:\.[0-9]{1,2})?", value):
        raise ValueError("Enter a USD amount with up to two decimals")
    whole, _, fractional = value.partition(".")
    cents = int(whole) * 100 + int((fractional + "00")[:2])
    if cents > 1000000 or (not allow_zero and cents == 0):
        raise ValueError("Invalid spending limit")
    return cents * 10000


def validate(payload):
    if isinstance(payload, dict) and set(payload) == set(DEFAULTS) - {'model_config'}:
        payload = {**payload, 'model_config': None}
    if not isinstance(payload, dict) or set(payload) != set(DEFAULTS):
        raise ValueError("Invalid AI settings")
    if any(type(payload[key]) is not bool for key in ("enabled", "diagnostics", "show_proposals")):
        raise ValueError("Invalid AI toggle")
    if not isinstance(payload["model"], str) or not MODEL.fullmatch(payload["model"]):
        raise ValueError("Invalid model ID")
    if type(payload["max_actions"]) is not int or not 1 <= payload["max_actions"] <= 8:
        raise ValueError("Invalid action count")
    domains = payload["allowed_domains"]
    if not isinstance(domains, list) or len(domains) != len(set(domains)) or not set(domains) <= DOMAINS:
        raise ValueError("Invalid allowed domains")
    if (payload["confirmation"] != "sensitive" or payload["routines"] != "mapped"
            or payload["ambiguous"] != "clarify"):
        raise ValueError("Unsupported safety policy")
    monthly = _money(payload["monthly_budget_usd"], allow_zero=True)
    ceiling = _money(payload["request_ceiling_usd"], allow_zero=False)
    profile = payload['model_config']
    if profile is not None or payload['enabled'] or payload['model'] in RATES:
        profile = model_profile(payload['model'], profile)
    if payload["enabled"] and (monthly < ceiling or not domains):
        raise ValueError("Budget or permitted devices not configured")
    return {**payload, 'model_config': profile}


def read():
    with database() as db:
        db.execute("CREATE TABLE IF NOT EXISTS ai_settings (id INTEGER PRIMARY KEY CHECK (id=1), document TEXT NOT NULL)")
        row = db.execute("SELECT document FROM ai_settings WHERE id=1").fetchone()
    return validate(json.loads(row[0]) if row else dict(DEFAULTS))


def save(payload):
    settings = validate(payload)
    if settings['enabled']:
        require_available(settings['model_config'])
    with database() as db:
        db.execute("CREATE TABLE IF NOT EXISTS ai_settings (id INTEGER PRIMARY KEY CHECK (id=1), document TEXT NOT NULL)")
        db.execute("INSERT OR REPLACE INTO ai_settings VALUES (1, ?)", (json.dumps(settings, sort_keys=True),))
    return settings
