"""Resolve media-search conversation agents without routing Declan into itself."""

import json
import re
from urllib.error import HTTPError
from urllib.request import Request


ENTITY_ID = re.compile(r"conversation\.[a-z0-9_]+")
# Legacy integrations remain discovery candidates for installations not
# configured with an explicit media-search provider. Declan's own conversation
# integration is NEVER a media search target.
AGENT_TEMPLATE = (
    "{% set legacy = integration_entities('declan_local') + integration_entities('jarvis_local') %}"
    "{% set self_agents = integration_entities('declan_two') %}"
    "{{ {'legacy': states.conversation | rejectattr('state', 'eq', 'unavailable') "
    "| map(attribute='entity_id') | select('in', legacy) | list, "
    "'self': self_agents} | to_json }}"
)


class MediaAgentError(ValueError):
    """A configured media agent is unavailable or cannot be verified."""


def resolve(connection, configured):
    """Return an independent HA conversation entity or a clear configuration error."""
    if configured and not ENTITY_ID.fullmatch(configured):
        raise MediaAgentError("Select a valid conversation entity for media search.")
    url, headers, opener = connection
    request = Request(url + "/api/template", headers=headers,
                      data=json.dumps({"template": AGENT_TEMPLATE}).encode())
    try:
        with opener.open(request, timeout=1.5) as response:
            payload = json.loads(response.read(65536))
    except HTTPError as error:
        error.close()
        raise MediaAgentError("I couldn't check Home Assistant media-search agents.") from None
    except (OSError, ValueError, TypeError):
        raise MediaAgentError("I couldn't check Home Assistant media-search agents.") from None
    if (not isinstance(payload, dict)
            or not isinstance(payload.get("legacy"), list)
            or not isinstance(payload.get("self"), list)):
        raise MediaAgentError("Home Assistant returned an invalid media-agent inventory.")
    self_agents = {agent for agent in payload["self"] if isinstance(agent, str)}
    if configured:
        if configured in self_agents:
            raise MediaAgentError("Declan cannot use its own conversation agent for media search.")
        # A separately configured agent may be from any HA integration, but
        # verify it is available rather than assuming a legacy integration.
        state_request = Request(url + "/api/states/" + configured, headers=headers)
        try:
            with opener.open(state_request, timeout=1.5) as response:
                state = json.loads(response.read(8192))
        except HTTPError as error:
            error.close()
            raise MediaAgentError("The configured media-search agent is unavailable.") from None
        except (OSError, ValueError, TypeError):
            raise MediaAgentError("The configured media-search agent is unavailable.") from None
        if (not isinstance(state, dict) or state.get("entity_id") != configured
                or state.get("state") in (None, "unavailable", "unknown")):
            raise MediaAgentError("The configured media-search agent is unavailable.")
        return configured

    candidates = {
        agent for agent in payload["legacy"]
        if isinstance(agent, str) and ENTITY_ID.fullmatch(agent) and agent not in self_agents
    }
    if not candidates:
        raise MediaAgentError("No independent media-search conversation agent was found. Set DECLAN_MEDIA_SEARCH_AGENT.")
    if len(candidates) != 1:
        raise MediaAgentError("Multiple media-search agents were found. Set DECLAN_MEDIA_SEARCH_AGENT.")
    return candidates.pop()
