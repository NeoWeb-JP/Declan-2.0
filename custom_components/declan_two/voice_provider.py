"""Generate audio through an existing Home Assistant TTS entity.

Reuses the provider's configured credentials. No ElevenLabs API key is stored
by Home Voice Assistant. The caller chooses a concrete provider entity such as
`tts.elevenlabs`; it must not be the Declan wrapper itself.
"""
from __future__ import annotations

import asyncio

from homeassistant.components import tts
from homeassistant.exceptions import HomeAssistantError

PROVIDER_TIMEOUT_SECONDS = 30


async def generate_from_existing_tts(
    hass, *, provider_entity_id: str, text: str,
    language: str | None = None, options: dict | None = None,
) -> tuple[str, bytes]:
    """Fetch provider audio using the supported Home Assistant media-source API."""
    if not provider_entity_id.startswith("tts."):
        raise ValueError("Provider must be a TTS entity")
    if not text or not text.strip():
        raise ValueError("Speech text must not be empty")
    media_source_id = tts.generate_media_source_id(
        hass, text, engine=provider_entity_id, language=language,
        options=options or {}, cache=True,
    )
    # Bound both paid and local provider requests, including explicit phrase
    # preparation. A hung provider must not prevent the fallback from running.
    async with asyncio.timeout(PROVIDER_TIMEOUT_SECONDS):
        extension, audio = await tts.async_get_media_source_audio(hass, media_source_id)
    if extension not in {"mp3", "wav", "ogg", "flac"}:
        raise HomeAssistantError("Unsupported TTS audio format")
    if not audio:
        raise HomeAssistantError("TTS provider returned no audio")
    return extension, audio
