"""Conservative OpenAI token charges, in integer micro-USD.

Rates are standard text API USD per million tokens. Unrecognised models,
missing usage or invalid counts retain the full pre-reserved request ceiling.
"""
from datetime import date, datetime, timezone
import re

RATES = {
    "gpt-5-mini": (250000, 2000000),
    "gpt-6-luna": (100000, 500000),
}


class RetiredModelError(ValueError):
    """Owner lifecycle settings prohibit starting another model request."""


def _rate(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,3})(?:\.[0-9]{1,6})?', value):
        raise ValueError("Enter a positive token price with up to six decimals")
    whole, _, fraction = value.partition('.')
    amount = int(whole) * 1000000 + int((fraction + '000000')[:6])
    if not 0 < amount <= 1000000000:
        raise ValueError("Token price must be above zero and at most 1000 USD per million")
    return amount


def model_profile(model, profile=None):
    """Return a fresh, validated profile bound to exactly one model ID."""
    if not isinstance(model, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}', model):
        raise ValueError("Invalid model ID")
    if profile is None:
        if model not in RATES:
            raise ValueError("Configure prices and capabilities for the selected model")
        inputs, outputs = RATES[model]
        profile = {'model': model, 'input_usd_per_million': f'{inputs / 1000000:.6f}',
                   'output_usd_per_million': f'{outputs / 1000000:.6f}',
                   'reasoning_effort': 'low', 'status': 'deprecated' if model == 'gpt-5-mini' else 'active',
                   'retire_on': ''}
    if (not isinstance(profile, dict) or set(profile) != {
            'model', 'input_usd_per_million', 'output_usd_per_million',
            'reasoning_effort', 'status', 'retire_on'} or profile['model'] != model):
        raise ValueError("Pricing profile must match the selected model")
    _rate(profile['input_usd_per_million'])
    _rate(profile['output_usd_per_million'])
    if profile['reasoning_effort'] not in ('', 'none', 'minimal', 'low', 'medium', 'high'):
        raise ValueError("Invalid model reasoning setting")
    if profile['status'] not in ('active', 'deprecated', 'retired'):
        raise ValueError("Invalid model lifecycle status")
    retirement = profile['retire_on']
    if not isinstance(retirement, str) or (retirement and (
            len(retirement) != 10 or date.fromisoformat(retirement).isoformat() != retirement)):
        raise ValueError("Invalid model retirement date")
    return dict(profile)


def require_available(profile):
    """Owner-supplied retirement dates are enforced at request time, in UTC."""
    if profile['status'] == 'retired' or (profile['retire_on'] and
            profile['retire_on'] <= datetime.now(timezone.utc).date().isoformat()):
        raise RetiredModelError("The configured AI model is retired; update AI settings")


def rate_pair(model, profile=None):
    configured = model_profile(model, profile)
    return _rate(configured['input_usd_per_million']), _rate(configured['output_usd_per_million'])


def charge(model, usage, *, profile=None):
    if not isinstance(usage, dict):
        raise ValueError("Model pricing is not configured")
    inputs, outputs = usage.get("input_tokens"), usage.get("output_tokens")
    if type(inputs) is not int or inputs < 0 or type(outputs) is not int or outputs < 0:
        raise ValueError("Missing token usage")
    input_rate, output_rate = rate_pair(model, profile)
    return (inputs * input_rate + outputs * output_rate + 999999) // 1000000
