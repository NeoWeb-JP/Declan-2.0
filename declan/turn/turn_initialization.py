"""Initialize a voice turn with capture arbitration and scoped session context."""
from dataclasses import dataclass

from declan.voice import assist_capture_http
from declan.http import request_origin
from declan.turn import session_context_access


@dataclass(frozen=True)
class InitializedTurn:
    source: str
    scope: str
    origin_device: str | None
    satellite: str | None
    recent_context: tuple


def prepare(handler, body, *, message, session_id, arbiter, normalize,
            new_session_id, sessions, lock, now, idle_seconds, retrieve):
    source, scope, origin_device, satellite = request_origin.request_context(
        handler.path, body,
    )
    if assist_capture_http.suppress_duplicate(
        handler, source=source, body=body, message=message,
        session_id=session_id, satellite=satellite, origin_device=origin_device,
        arbiter=arbiter, normalize=normalize, new_session_id=new_session_id,
    ):
        return None
    recent_context = session_context_access.load_recent_context(
        session_id=session_id, scope=scope, sessions=sessions,
        lock=lock, now=now, idle_seconds=idle_seconds, retrieve=retrieve,
    )
    return InitializedTurn(
        source=source, scope=scope, origin_device=origin_device,
        satellite=satellite, recent_context=recent_context,
    )
