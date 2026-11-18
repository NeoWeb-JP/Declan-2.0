"""Visible transcript with legacy in-process speaker metadata.

String operations create plain strings and cannot preserve this metadata. Consumers
must extract speaker/capture metadata before normalizing or transforming text.
"""


from dataclasses import dataclass
import math


@dataclass(frozen=True)
class SpeakerMetadata:
    """Explicit per-request identity snapshot, independent of transcript text."""

    speaker: str | None
    capture_level: dict[str, float] | None


def metadata_from_transcript(transcript):
    """Snapshot identity before string operations can discard its attributes."""
    capture = getattr(transcript, "capture_level", None)
    return SpeakerMetadata(
        speaker=speaker_from_transcript(transcript),
        capture_level=dict(capture) if isinstance(capture, dict) else None,
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


def speaker_request_payload(transcript):
    """Project transcript identity into the existing Assist JSON contract."""
    metadata = metadata_from_transcript(transcript)
    payload = {}
    speaker = metadata.speaker
    if isinstance(speaker, tuple) and len(speaker) == 3:
        interaction_id, name, confidence = speaker
        if (isinstance(interaction_id, str) and isinstance(name, str)
                and type(confidence) in (int, float) and 0 <= confidence <= 1):
            payload["speaker"] = {
                "interaction_id": interaction_id,
                "name": name,
                "confidence": confidence,
            }
    elif hasattr(transcript, "speaker") or hasattr(transcript, "jarvis_speaker"):
        payload["speaker"] = {}
    if isinstance(metadata.capture_level, dict):
        capture = metadata.capture_level
        # Only forward the numeric fields produced by CaptureLevel.snapshot().
        # Arbitrary provider objects must not break JSON serialization.
        if all(type(capture.get(key)) in (int, float)
               and math.isfinite(capture[key]) and capture[key] >= 0
               for key in ("ended_at", "duration", "rms")):
            payload["capture"] = {key: capture[key]
                                  for key in ("ended_at", "duration", "rms")}
    return payload
