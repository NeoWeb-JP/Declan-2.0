"""Visible transcript with legacy in-process speaker metadata.

String operations create plain strings and cannot preserve this metadata. Consumers
must extract speaker/capture metadata before normalizing or transforming text.
"""


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
