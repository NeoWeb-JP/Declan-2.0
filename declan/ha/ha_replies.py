"""Reading Home Assistant's JSON replies without tripping over a big house.

When HA runs a service, its reply lists every state that changed meanwhile. In a
busy house that list can be far larger than Declan's read limits, so the reply
was cut off and couldn't be parsed. The action had worked, but Declan said
"I couldn't reach…" (26 Nov 2026: "add milk to the shopping list"). Service
calls that don't ask for a response now ignore the reply; ones that do
(``?return_response``) get a larger limit.
"""
import json

SERVICE_RESPONSE_LIMIT = 4 * 1024 * 1024


def decode(response, path, limit):
    """The decoded JSON for ``path``, or [] for a plain service call (the call worked)."""
    if "/api/services/" in path:
        if "return_response" not in path:
            return []
        limit = max(limit, SERVICE_RESPONSE_LIMIT)
    return json.loads(response.read(limit) or b"null")
