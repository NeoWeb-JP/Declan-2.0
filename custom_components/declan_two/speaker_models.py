"""Visible transcript with legacy in-process speaker metadata.

String operations create plain strings and cannot preserve this metadata. Consumers
must extract speaker/capture metadata before normalizing or transforming text.
"""


from dataclasses import dataclass
import math


@dataclass(frozen=True)
class SpeakerMetadata:
    """Explicit per-request identity snapshot, independent of transcript text."""

    speaker: tuple[str, str, float] | str | None
    capture_level: dict[str, float] | None


def metadata_from_transcript(transcript):
    """Snapshot identity before string operations can discard its attributes."""
    capture = getattr(transcript, "capture_level", None)
    # Snapshot provider-owned mappings so later mutation cannot change a turn.
    capture_snapshot = dict(capture) if type(capture) is dict else None
    return SpeakerMetadata(
        speaker=speaker_from_transcript(transcript),
        capture_level=capture_snapshot,
    )


class SpeakerTranscript(str):
    """Compatibility carrier for existing Home Assistant STT consumers."""

    capture_level: dict[str, float] | None

    def __new__(cls, text, speaker=None, capture_level=None):
        obj = super().__new__(cls, text)
        obj.speaker = speaker
        obj.capture_level = capture_level
        return obj

    @property
    def jarvis_speaker(self):
        """Legacy attribute retained for existing voice pipeline consumers."""
        return self.speaker

    @jarvis_speaker.setter
    def jarvis_speaker(self, value):
        self.speaker = value

    def __reduce_ex__(self, protocol):
        return (type(self), (str(self), self.speaker, self.capture_level))


def speaker_from_transcript(transcript):
    """Read speaker identity before any string normalization loses metadata.

    Prefer the canonical field while accepting older STT providers that still
    attach only the legacy attribute to a string subclass.
    """
    speaker = getattr(transcript, "speaker", None)
    if speaker is not None:
        return speaker
    return getattr(transcript, "jarvis_speaker", None)


def valid_wyoming_speaker(interaction_id, name, confidence) -> bool:
    """Accept a recognised Wyoming speaker, never an unknown identity marker."""
    return (
        type(interaction_id) is str and bool(interaction_id.strip())
        and len(interaction_id) <= 80
        and type(name) is str and bool(name.strip()) and len(name) <= 80
        and name.strip().casefold() not in {"unknown", "unidentified", "none"}
        and type(confidence) in (int, float) and 0 <= confidence <= 1
        and math.isfinite(confidence)
    )


def speaker_payload_from_metadata(metadata: SpeakerMetadata, *, speaker_present: bool = False):
    """Project explicit metadata into the existing Assist JSON contract."""
    payload: dict[str, object] = {}
    speaker = metadata.speaker
    if type(speaker) is tuple and len(speaker) == 3:
        interaction_id, name, confidence = speaker
        if valid_wyoming_speaker(interaction_id, name, confidence):
            payload["speaker"] = {
                "interaction_id": interaction_id,
                "name": name,
                "confidence": confidence,
            }
    elif speaker_present:
        payload["speaker"] = {}
    if type(metadata.capture_level) is dict:
        capture = metadata.capture_level
        # Preserve valid provider numeric fields while excluding objects that
        # would make the entire Assist JSON request fail serialization.
        safe_capture = {
            key: value for key, value in capture.items()
            if type(key) is str and key and type(value) in (int, float)
            and 0 <= value <= 1e308 and math.isfinite(value)
        }
        if safe_capture:
            payload["capture"] = safe_capture
    return payload


def transcript_for_ha(text: str, metadata: SpeakerMetadata) -> SpeakerTranscript:
    """Adapt explicit STT metadata to the current Home Assistant text contract.

    This is the only compatibility conversion needed by STT providers until an
    HA-supported side channel can replace the string subclass entirely.
    """
    return SpeakerTranscript(
        str(text), metadata.speaker,
        dict(metadata.capture_level) if metadata.capture_level is not None else None,
    )


def snapshot_speaker_payload(transcript):
    """Capture the HA conversation boundary metadata before text is normalised.

    Returns only JSON-compatible values; never stores request-specific state.
    A plain string deliberately produces no identity or capture payload.
    """
    metadata = metadata_from_transcript(transcript)
    return speaker_payload_from_metadata(
        metadata,
        speaker_present=(hasattr(transcript, "speaker")
                         or hasattr(transcript, "jarvis_speaker")),
    )


def speaker_request_payload(transcript):
    """Legacy transcript adapter for the explicit Assist metadata boundary."""
    return snapshot_speaker_payload(transcript)
