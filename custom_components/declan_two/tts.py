"""Declan's ElevenLabs-backed speech entity for Assist."""
import logging
import random
from pathlib import Path

from homeassistant.components.tts import TextToSpeechEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store

from .phrase_library import PhraseLibrary, normalise_audio, phrase_parts
from .voice_budget import VoiceBudget
from .voice_cache import VoiceCache
from .voice_defaults import DEFAULT_PROVIDER
from .voice_catalog_fallback import category_alternatives, load_catalogue
from .voice_provider import generate_from_existing_tts
from .voice_text import spoken_text

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.options.get("tts_enabled"):
        cache = VoiceCache(hass.config.path("jarvis_voice_cache"))
        budget = VoiceBudget(Store(hass, 1, f"declan_two.voice_usage.{entry.entry_id}"))
        await budget.load()
        async_add_entities([DeclanVoiceManager(entry, cache, budget)])


class DeclanVoiceManager(TextToSpeechEntity):
    _attr_name = "Declan 2.0 Voice Manager"
    _attr_supported_languages = ["en"]
    _attr_default_language = "en"

    def __init__(self, entry, cache, budget):
        self._attr_unique_id = f"{entry.entry_id}_voice_manager"
        self._entry = entry
        self._cache = cache
        self._budget = budget
        self._phrases = PhraseLibrary(cache, self._normalise)

    async def _normalise(self, extension, audio):
        from homeassistant.components.ffmpeg import get_ffmpeg_manager

        return await normalise_audio(extension, audio, get_ffmpeg_manager(self.hass).binary)

    async def async_get_tts_audio(self, message, language, options):
        config = self._entry.options
        provider = config.get("primary_tts", DEFAULT_PROVIDER)
        if provider == self.entity_id or provider.startswith(
            ("tts.jarvis_voice_manager", "tts.declan_voice_manager", "tts.declan_2_0_voice_manager")
        ):
            raise HomeAssistantError("Select a speech provider such as ElevenLabs")
        voice = config.get("elevenlabs_voice", "")
        provider_options = dict(options or {})
        if voice:
            provider_options["voice"] = voice
        identity = {
            "provider": provider,
            "voice_id": f"{config.get('cache_revision', 'v1')}:{voice}",
            "model": provider,
            "language": language or "en",
            "settings": provider_options,
        }

        async def generate(text=message):
            text = spoken_text(text)
            await self._budget.reserve(text, "primary", config.get("primary_daily_character_limit", 0))
            return await generate_from_existing_tts(
                self.hass, provider_entity_id=provider, text=text,
                language=language, options=provider_options,
            )

        cache_enabled = config.get("cache_enabled", True)
        try:
            if not cache_enabled:
                return await generate()
            if phrase_parts(message):
                whole = await self._cache.find_cached_audio(text=message, **identity)
                if whole:
                    return whole
                try:
                    extension, audio, _, _ = await self._phrases.compose(message, identity, generate)
                    return extension, audio
                except (ValueError, OSError, TimeoutError):
                    _LOGGER.warning("Phrase assembly unavailable; using whole-sentence TTS")
            extension, audio, _ = await self._cache.get_or_generate_audio(
                text=message, **identity, generate=generate,
            )
            return extension, audio
        except (HomeAssistantError, ValueError, OSError, TimeoutError) as err:
            _LOGGER.warning("Declan 2.0 TTS provider failed: %s", type(err).__name__)
            if cache_enabled and config.get("category_fallback", True):
                alternate = await self._cached_alternative(message, identity)
                if alternate is not None:
                    return alternate
            raise HomeAssistantError("Declan 2.0 could not generate speech") from None

    async def _cached_alternative(self, message, identity):
        try:
            catalogue = await self.hass.async_add_executor_job(
                load_catalogue, Path(__file__).with_name("responses.json"),
            )
        except (OSError, ValueError):
            return None

        state = self.hass.states.get("input_boolean.guest_mode")
        guest = state is None or state.state != "off"
        alternatives = list(category_alternatives(message, catalogue, guest=guest))
        random.shuffle(alternatives)
        for alternate in alternatives:
            cached = await self._cache.find_cached_audio(text=alternate, **identity)
            if cached is not None:
                return cached
        return None
