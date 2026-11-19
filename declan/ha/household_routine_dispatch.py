"""Home Assistant dispatch for dinner announcements and guest assignments.

Dependencies are supplied by server compatibility wrappers to retain patch points.
"""
import json
import re
import sqlite3
from urllib.error import HTTPError
from declan.core.execution_results import ExecutionResult, Outcome


def start_dinner_result(connection, *, approved=False, policy, registry, choose_response, guest_mode, request_factory):
    # Dinner is a non-safety announcement. Never dispatch it during
    # overnight quiet hours, even when explicitly requested.
    if not policy.overnight_announcement_allowed("dinner"):
        return ExecutionResult("Dinner announcements are muted between 23:00 and 07:00.", Outcome.SKIPPED)
    if connection is None:
        return ExecutionResult("The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED)
    try:
        dinner_mapping = registry.load().get("dinner")
    except (OSError, ValueError, sqlite3.Error):
        dinner_mapping = None
    if not dinner_mapping:
        return ExecutionResult("Map the Dinner script in Declan Settings.", Outcome.NOT_CONFIGURED)
    if dinner_mapping["sensitive"] and not approved:
        return ExecutionResult("Dinner routine requires explicit confirmation.", Outcome.UNRESOLVED)
    url, headers, opener = connection
    announcement = choose_response("dinner_announcement", guest_mode())
    request = request_factory(
        f"{url}/api/services/script/turn_on", headers=headers,
        data=json.dumps({
            "entity_id": dinner_mapping["script"], "variables": {"dinner_message": announcement},
        }).encode(), method="POST",
    )
    try:
        with opener.open(request, timeout=2):
            pass
    except HTTPError as error:
        error.close()
        if 400 <= error.code < 500:
            return ExecutionResult("Home Assistant rejected the dinner announcement request.", Outcome.UNAVAILABLE)
        return ExecutionResult("I couldn't confirm that Home Assistant accepted the dinner announcement request.", Outcome.UNVERIFIED)
    except OSError:
        return ExecutionResult("I couldn't confirm that Home Assistant accepted the dinner announcement request.", Outcome.UNVERIFIED)
    return ExecutionResult(announcement, Outcome.REQUESTED)


def guest_assignment_result(operation, connection, *, entities, sass, request_factory):
    if connection is None:
        return ExecutionResult("I couldn't reach Home Assistant to check Guest Mode or the guest register.", Outcome.UNAVAILABLE)
    try:
        guest_mode_entity = entities.guest_mode()
        guest_register_entity = entities.guest_register()
    except (OSError, sqlite3.Error, ValueError):
        return ExecutionResult("Guest Mode or the guest register is not configured correctly.", Outcome.NOT_CONFIGURED)
    url, headers, opener = connection

    def request(path, data=None):
        body = json.dumps(data).encode() if data is not None else None
        try:
            with opener.open(request_factory(url + path, headers=headers, data=body), timeout=1.5) as response:
                return json.loads(response.read(8192))
        except HTTPError as error:
            error.close()
        except (OSError, ValueError):
            pass
        return None

    def read_state(entity):
        payload = request(f"/api/states/{entity}")
        state = payload.get("state") if isinstance(payload, dict) else None
        if not isinstance(state, str) or state.strip().casefold() in {"unknown", "unavailable"}:
            return None
        return state.strip()

    if operation.startswith("assign:"):
        names = operation.partition(":")[2].strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z '\\-]{0,119}", names):
            return ExecutionResult("Tell me who is in charge.", Outcome.UNRESOLVED)
        request("/api/services/input_text/set_value", {"entity_id": guest_register_entity, "value": names})
        if read_state(guest_register_entity) != names:
            return ExecutionResult("I couldn't verify the guest register was updated, so Guest Mode was left unchanged.", Outcome.UNVERIFIED)
        request("/api/services/input_boolean/turn_on", {"entity_id": guest_mode_entity})
        if read_state(guest_mode_entity) != "on":
            return ExecutionResult("I updated the guest register, but couldn't verify Guest Mode is on.", Outcome.PARTIAL)
        return ExecutionResult(f"{names} are in charge. Guest Mode is on.", Outcome.CONFIRMED)

    if operation == "clear":
        request("/api/services/input_text/set_value", {"entity_id": guest_register_entity, "value": ""})
        names = read_state(guest_register_entity)
        # Keep Guest Mode in place until the register is verified empty.
        if names != "":
            return ExecutionResult("I couldn't verify that the guest register was cleared, so I left Guest Mode alone.", Outcome.UNVERIFIED)
        request("/api/services/input_boolean/turn_off", {"entity_id": guest_mode_entity})
        if read_state(guest_mode_entity) != "off":
            return ExecutionResult("I cleared the guest register, but couldn't verify that Guest Mode is off.", Outcome.PARTIAL)
        return ExecutionResult(sass("I cleared the guest register and turned off Guest Mode.", "guest_cleared", "off"), Outcome.CONFIRMED)

    mode = read_state(guest_mode_entity)
    names = read_state(guest_register_entity)
    if mode not in {"on", "off"} or names is None:
        return ExecutionResult("I couldn't read Guest Mode or the guest register.", Outcome.UNAVAILABLE)
    if mode == "on":
        if names:
            return ExecutionResult(f"Currently in charge: {names}. Guest Mode is on.", Outcome.CONFIRMED)
        return ExecutionResult("Guest Mode is on, but nobody is listed in the guest register.", Outcome.CONFIRMED)
    if names:
        return ExecutionResult(f"Guest Mode is off, but the guest register still lists {names}.", Outcome.CONFIRMED)
    return ExecutionResult(sass("Guest Mode is off. The house is back in your hands.", "guest_inactive", mode), Outcome.CONFIRMED)
