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
