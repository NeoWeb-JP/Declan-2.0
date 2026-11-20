"""Owner speaker-recognition threshold, editable in Settings -> Voice & learning.

VOI-08: a VoicePipeline speaker match counts as "recognised" only at or above
this confidence (0-1 scale, the same scale VoicePipeline reports as average
confidence). The default stays 0.85. A value saved in Settings wins, then
DECLAN_SPEAKER_THRESHOLD, then the default.

Sensitive-routine voice confirmations (DECLAN_TRUSTED_SPEAKERS) deliberately do
not use this value: they keep their fixed 0.85 floor so lowering the threshold
for History labels and capture arbitration never weakens a security check.
"""
import json
import math
import os
from pathlib import Path

ENVIRONMENT = "DECLAN_SPEAKER_THRESHOLD"
DEFAULT = 0.85
MINIMUM = 0.30
MAXIMUM = 0.99
# History used a gentler 0.75 for display labels before this setting existed.
HISTORY_DISPLAY_CEILING = 0.75
PATH = Path(__file__).resolve().parents[2] / ".data" / "speaker-settings.json"


def _valid(value):
    return (type(value) in (int, float) and math.isfinite(value)
            and MINIMUM <= value <= MAXIMUM)


def _environment():
    raw = os.environ.get(ENVIRONMENT, "").strip()
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if _valid(value) else None


def _saved(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return None
    value = data.get("threshold") if isinstance(data, dict) else None
    return value if _valid(value) else None


def listing(path=None):
    path = PATH if path is None else path
    saved = _saved(path)
    if saved is not None:
        return {"threshold": saved, "source": "saved", "default": DEFAULT}
    environment = _environment()
    if environment is not None:
        return {"threshold": environment, "source": "environment", "default": DEFAULT}
    return {"threshold": DEFAULT, "source": "default", "default": DEFAULT}


def threshold(path=None):
    """Recognised-speaker threshold for capture arbitration and History."""
    return listing(path)["threshold"]


def history_threshold(path=None):
    """History label threshold: never stricter than the original 0.75."""
    return min(HISTORY_DISPLAY_CEILING, threshold(path))


def save(payload, path=None):
    path = Path(PATH if path is None else path)
    if not isinstance(payload, dict) or set(payload) != {"threshold"} or not _valid(payload["threshold"]):
        raise ValueError(f"Enter a speaker threshold from {MINIMUM:.2f} to {MAXIMUM:.2f}.")
    value = round(float(payload["threshold"]), 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps({"threshold": value}) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return listing(path)
