"""Home Assistant area lookup and explicitly marked switch-as-light actions.

Keep transport, timeouts and action evidence semantics unchanged.
"""
import json
import re
from urllib.error import HTTPError
from urllib.request import Request

from execution_results import ExecutionResult, Outcome
from lighting_action_evidence import LightingActionEvidence, LightingActionStatus
from action_evidence_buffer import append_action_evidence


def read_ha_areas(connection, origin=None, *, request_factory=Request):
    url, headers, opener = connection
    template = (
        "{% set result = namespace(areas=[]) %}"
        "{% for id in areas() %}"
        "{% set result.areas = result.areas + [[area_name(id), area_entities(id)]] %}"
        "{% endfor %}{{ result.areas | to_json }}"
    )
    if origin is not None:
        template = (
            "{% set room = area_id(" + json.dumps(origin) + ") %}"
            "{{ ([[area_name(room), area_entities(room)]] if room else []) | to_json }}"
        )
    request = request_factory(f"{url}/api/template", headers=headers,
                      data=json.dumps({"template": template}).encode(), method="POST")
    try:
        with opener.open(request, timeout=1.5) as response:
            rows = json.loads(response.read(1024 * 1024))
        if not isinstance(rows, list):
            return {}
        areas = {}
        for label, entities in rows:
            if not isinstance(label, str) or not isinstance(entities, list):
                return {}
            areas.setdefault(" ".join(label.casefold().split()), set()).update(entities)
        if "master bedroom" in areas:
            areas.setdefault("bedroom", areas["master bedroom"])
        if "study" in areas:
            areas.setdefault("office", areas["study"])
        if "living room" in areas:
            areas.setdefault("lounge", areas["living room"])
        elif "lounge" in areas:
            areas.setdefault("living room", areas["lounge"])
        return areas
    except HTTPError as error:
        error.close()
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        pass
    return {}



def set_switch_as_light_result(name, desired_state, inventory, connection, *, preview=False, action_results=None, request_factory=Request, append_evidence=append_action_evidence, evidence_factory=LightingActionEvidence):
    """Only switch entities explicitly marked as lights may receive light commands."""
    if desired_state not in {"on", "off"}:
        return None
    eligible = []
    for row in inventory:
        entity = row.get("entity_id", "") if isinstance(row, dict) else ""
        attributes = row.get("attributes", {}) if isinstance(row, dict) else {}
        if not re.fullmatch(r"switch\.[a-z0-9_]+", entity) or not isinstance(attributes, dict):
            continue
        if attributes.get("declan_as_light") is not True:
            continue
        label = str(attributes.get("friendly_name") or entity.split(".", 1)[1].replace("_", " ")).casefold()
        if name.casefold() in {label, entity.casefold(), entity.split(".", 1)[1].replace("_", " ")}:
            eligible.append((entity, row.get("state"), label))
    if not eligible:
        return None
    if len(eligible) != 1:
        return ExecutionResult("More than one marked light switch matches. Please use its exact entity ID.", Outcome.UNRESOLVED)
    entity, previous, label = eligible[0]
    if previous not in {"on", "off"}:
        return ExecutionResult(f"{label} is unavailable in Home Assistant.", Outcome.UNAVAILABLE)
    if preview:
        return ExecutionResult(f"Preview: I would turn {desired_state} {label}.", Outcome.PREVIEW)
    if previous == desired_state:
        return ExecutionResult(f"{label} is already {desired_state}.", Outcome.CONFIRMED)
    url, headers, opener = connection
    request = request_factory(f"{url}/api/services/switch/turn_{desired_state}", headers=headers,
                      data=json.dumps({"entity_id": entity}).encode(), method="POST")
    try:
        with opener.open(request, timeout=4) as response:
            response.read(4096)
        state_request = request_factory(f"{url}/api/states/{entity}", headers=headers)
        with opener.open(state_request, timeout=4) as response:
            observed = json.loads(response.read(8192))
        verified = isinstance(observed, dict) and observed.get("state") == desired_state
    except HTTPError as error:
        error.close()
        verified = False
    except (OSError, ValueError):
        verified = False
    if action_results is not None:
        evidence = evidence_factory(label, "turn_" + desired_state,
                                          LightingActionStatus.CONFIRMED if verified else LightingActionStatus.UNVERIFIED,
                                          entity_id=entity)
        append_evidence(action_results, evidence)
    return ExecutionResult(f"{label} is {desired_state}." if verified else f"I couldn't verify {label} is {desired_state}.", Outcome.CONFIRMED if verified else Outcome.UNVERIFIED)

