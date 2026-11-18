"""Independent locks for sensitive external writes and credential updates."""

from threading import Lock


class SensitiveWriteState:
    """Serialize each sensitive write domain without cross-service blocking."""

    def __init__(self):
        self.voice_reviews = Lock()
        self.ai_credentials = Lock()


DEFAULT_SENSITIVE_WRITE_STATE = SensitiveWriteState()
