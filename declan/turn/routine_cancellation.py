"""Cancellation of active mapped Home Assistant routines."""

import json
from urllib.error import HTTPError
from urllib.request import Request

from declan.core.execution_results import ExecutionResult, Outcome


def stop_pending_routines_result(*, connection_factory, active_registry):
    """Request cancellation of each active script without claiming rollback."""
    connection = connection_factory()
    if connection is None:
        return ExecutionResult("Home Assistant is not connected.", Outcome.NOT_CONFIGURED), None
    active = active_registry.snapshot()
    if not active:
        return ExecutionResult("No mapped routine is currently awaiting completion.", Outcome.CONFIRMED), None
    url, headers, opener = connection
    stopped, unknown = [], []
    for name, script in active.items():
        request = Request(f"{url}/api/services/script/turn_off", headers=headers,
                          data=json.dumps({"entity_id": script}).encode(), method="POST")
        try:
            with opener.open(request, timeout=4) as response:
                response.read(4096)
            stopped.append(name)
        except HTTPError as error:
            error.close()
            unknown.append(name)
        except (OSError, ValueError):
            unknown.append(name)
    message = ("Cancellation requested for: " + ", ".join(stopped) + ". " if stopped else "")
    if unknown:
        message += "Could not confirm cancellation request for: " + ", ".join(unknown) + "."
    message += " Already completed actions were not rolled back."
    return ExecutionResult(message, Outcome.UNVERIFIED if unknown or stopped else Outcome.CONFIRMED), None
