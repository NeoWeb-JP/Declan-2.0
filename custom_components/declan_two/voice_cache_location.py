"""Select a Declan TTS cache directory without abandoning legacy cached audio."""

from pathlib import Path


def select_cache_directory(config_path):
    """Reuse an existing Jarvis cache; use the Declan name for new installs."""
    legacy = Path(config_path("jarvis_voice_cache"))
    current = Path(config_path("declan_voice_cache"))
    # Do not migrate/remove the legacy directory as part of the rename:
    # retaining it avoids re-generating charged provider audio.
    return legacy if legacy.exists() else current
