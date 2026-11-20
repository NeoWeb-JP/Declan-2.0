"""Assist capture arbitration and duplicate HTTP response handling."""
from declan.voice import speaker_settings


def trusted_speaker_name(speaker):
    """Only use a sufficiently confident, named speaker for capture arbitration."""
    if (
        isinstance(speaker, dict)
        and type(speaker.get("confidence")) in (int, float)
        and speaker["confidence"] >= speaker_settings.threshold()
        and isinstance(speaker.get("name"), str)
    ):
        return speaker["name"]
    return None


def suppress_duplicate(handler, *, source, body, message, session_id,
                       satellite, origin_device, arbiter, normalize, new_session_id):
    """Return True when a duplicate Assist capture has been answered."""
    if source != "assist":
        return False
    speaker_name = trusted_speaker_name(body.get("speaker"))
    if arbiter.claim(
        normalize(message), satellite or origin_device,
        body.get("capture"), speaker_name,
    ):
        return False
    handler.send_json(
        200,
        {"reply": "", "session_id": session_id or new_session_id(24),
         "outcome": "duplicate"},
    )
    return True
