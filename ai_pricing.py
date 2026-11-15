"""Conservative OpenAI token charges, in integer micro-USD.

Rates are standard text API USD per million tokens. Unrecognised models,
missing usage or invalid counts retain the full pre-reserved request ceiling.
"""
RATES = {
    "gpt-5-mini": (250000, 2000000),
    "gpt-6-luna": (100000, 500000),
}


def charge(model, usage):
    if model not in RATES or not isinstance(usage, dict):
        raise ValueError("Model pricing is not configured")
    inputs, outputs = usage.get("input_tokens"), usage.get("output_tokens")
    if any(type(value) is not int or value < 0 for value in (inputs, outputs)):
        raise ValueError("Missing token usage")
    input_rate, output_rate = RATES[model]
    return (inputs * input_rate + outputs * output_rate + 999999) // 1000000
