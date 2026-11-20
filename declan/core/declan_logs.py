"""Bounded, redacted Declan application log feed for the native HA Settings panel."""
from datetime import datetime, timezone
import logging
import re
from declan.core.log_feed_state import LogFeedState

STATE = LogFeedState()
_SENSITIVE = re.compile(
    r"(?i)(bearer\s+)[a-z0-9._~+/-]+|"
    r"((?:client_secret|api_key|access_token|refresh_token|password|authorization)"
    r"\s*[:=]\s*['\"]?(?:Bearer\s+)?)[^\s,'\"}]+"
)
_NAMES = {"spotify_playlists", "music", "server", "declan_logs"}


def _safe(message):
    return _SENSITIVE.sub(lambda match: (match.group(1) or match.group(2)) + "[REDACTED]", message)[:1000]


class _Capture(logging.Handler):
    def emit(self, record):
        if record.name not in _NAMES and not record.name.startswith("declan"):
            return
        # Avoid unrelated root logger noise; keep meaningful Declan warnings and errors.
        if record.levelno < logging.INFO:
            return
        try:
            message = _safe(record.getMessage())
        except (TypeError, ValueError):
            return
        item = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "source": record.name[:80],
            "message": message,
            "levelno": record.levelno,
        }
        STATE.append(item)


class _Journal(logging.StreamHandler):
    """Declan warnings and errors on stderr, so `journalctl -u declan` shows them.

    Once the panel feed handler is on the root logger, Python no longer prints
    warnings anywhere else, so without this they were visible only in the panel.
    """
    def __init__(self, stream=None):
        super().__init__(stream)
        self.setLevel(logging.WARNING)
        self.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    def filter(self, record):
        return record.name in _NAMES or record.name.startswith("declan")

    def format(self, record):
        return _safe(super().format(record))


_JOURNAL: list[logging.Handler] = []


def install(stream=None):
    root = logging.getLogger()
    STATE.install(root, _Capture)
    if not _JOURNAL:
        _JOURNAL.append(_Journal(stream))
    if _JOURNAL[0] not in root.handlers:
        root.addHandler(_JOURNAL[0])


def recent(level="ALL", limit=200):
    if level not in {"ALL", "INFO", "WARNING", "ERROR"}:
        raise ValueError("Invalid log level")
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("Invalid log limit")
    threshold = {"ALL": 0, "INFO": 20, "WARNING": 30, "ERROR": 40}[level]
    return STATE.snapshot(threshold=threshold, limit=limit)
