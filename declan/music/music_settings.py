"""Owner music behaviour settings, editable in the native panel.

A value saved in Settings wins. Without one, the environment variable applies
(so existing installs keep their declan.env choice), then the built-in default.
"""
import json
import os
from pathlib import Path

# setting -> (environment variable, default, values that turn it on/off)
SETTINGS = {
    "reply_first": ("DECLAN_MUSIC_REPLY_FIRST", True),
    "music_assistant_search": ("DECLAN_MUSIC_ASSISTANT_SEARCH", False),
}
# Percentage music starts at (louder speakers are turned down first); 0 is off.
START_VOLUME = ("DECLAN_MUSIC_START_VOLUME", 30)
_ON = frozenset({"1", "true", "yes", "on"})
_OFF = frozenset({"0", "false", "no", "off"})


def _environment(name, default):
    value = os.environ.get(name, "").strip().lower()
    if value in _ON:
        return True
    if value in _OFF:
        return False
    return default


def _file(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _saved(path):
    return {key: value for key, value in _file(path).items() if key in SETTINGS and type(value) is bool}


def _valid_percent(value):
    return type(value) is int and 0 <= value <= 100


def start_volume(path):
    """(percent, source): saved in Settings, else DECLAN_MUSIC_START_VOLUME, else 30."""
    saved = _file(path).get("start_volume")
    if _valid_percent(saved):
        return saved, "saved"
    name, default = START_VOLUME
    raw = os.environ.get(name, "").strip()
    try:
        value = int(raw)
    except ValueError:
        return default, "default"
    return min(100, max(0, value)), "environment"


def enabled(path, key):
    saved = _saved(path)
    if key in saved:
        return saved[key]
    name, default = SETTINGS[key]
    return _environment(name, default)


def listing(path):
    saved = _saved(path)
    settings, sources = {}, {}
    for key, (name, default) in SETTINGS.items():
        if key in saved:
            settings[key], sources[key] = saved[key], "saved"
        else:
            settings[key] = _environment(name, default)
            sources[key] = "environment" if os.environ.get(name, "").strip().lower() in _ON | _OFF else "default"
    percent, source = start_volume(path)
    # Kept outside "settings"/"sources", whose exact keys older panels validate.
    return {"settings": settings, "sources": sources,
            "start_volume": {"percent": percent, "source": source}}


def save(path, payload, start_volume_percent=None):
    if (not isinstance(payload, dict) or set(payload) != set(SETTINGS)
            or any(type(value) is not bool for value in payload.values())):
        raise ValueError("Send true or false for every music setting.")
    if start_volume_percent is not None and not _valid_percent(start_volume_percent):
        raise ValueError("Start volume must be a whole number from 0 to 100.")
    kept = _file(path).get("start_volume")
    if start_volume_percent is not None:
        payload = {**payload, "start_volume": start_volume_percent}
    elif _valid_percent(kept):
        # An older panel saves only the switches; keep the saved start volume.
        payload = {**payload, "start_volume": kept}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return listing(path)
