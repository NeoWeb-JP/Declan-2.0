"""Declan's ElevenLabs-backed speech entity for Assist.

REL-01 order: persistent cache, then the primary provider (ElevenLabs), then a
cached equivalent reply, then the optional local TTS entity (for example
tts.piper). Local audio is cached under its own identity, so it never replaces
or masquerades as primary-voice audio.
"""
import logging
import random
from pathlib import Path

from homeassistant.components.tts import TextToSpeechEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store

from .phrase_library import PhraseLibrary, normalise_audio, phrase_parts
from .voice_budget import VoiceBudget
from .voice_cache import VoiceCache
from .voice_cache_location import select_cache_directory
from .voice_defaults import DEFAULT_PROVIDER
from .guest_mode_policy import DEFAULT_GUEST_MODE_ENTITY, guest_safe
from .household_view import guest_tone
from .voice_catalog_fallback import category_alternatives, load_catalogue
from .voice_provider import generate_from_existing_tts
from .voice_text import spoken_text
from .quiet_speech import quiet_hours, attenuate_wav

_LOGGER = logging.getLogger(__name__)
_WRAPPERS = ("tts.jarvis_voice_manager", "tts.declan_voice_manager", "tts.declan_2_0_voice_manager")


def local_provider(config, primary, own_entity_id=None):
    """The configured local fallback entity, or None when unset or unusable."""
    value = config.get("local_tts", "")
    value = value.strip() if isinstance(value, str) else ""
    if (not value or not value.startswith("tts.") or value == primary
            or value == own_entity_id or value.startswith(_WRAPPERS)):
        return None
    return value


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.options.get("tts_enabled"):
        cache = VoiceCache(select_cache_directory(hass.config.path))
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

    async def async_will_remove_from_hass(self):
        """Flush any buffered fallback accounting on a clean HA unload."""
        if not await self._budget.flush():
            _LOGGER.warning("Declan voice usage could not be saved on unload")
        await super().async_will_remove_from_hass()

    async def _normalise(self, extension, audio):
        from homeassistant.components.ffmpeg import get_ffmpeg_manager

        return await normalise_audio(extension, audio, get_ffmpeg_manager(self.hass).binary)

    async def _night_speech(self, result):
        # The HA timezone, not the container timezone, defines quiet hours.
        from datetime import datetime
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        zone_name = getattr(getattr(self.hass, "config", None), "time_zone", None)
        try:
            now = datetime.now(ZoneInfo(zone_name)) if zone_name else datetime.now().astimezone()
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            # If the household clock cannot be trusted, keep speech quiet
            # rather than accidentally playing it at daytime amplitude.
            _LOGGER.warning("Invalid Home Assistant timezone; attenuating speech")
            now = datetime.now().astimezone().replace(hour=23, minute=0)
        if not quiet_hours(now):
            return result
        from homeassistant.components.ffmpeg import get_ffmpeg_manager
        from .phrase_library import normalise_audio

        extension, audio = result
        pcm = await normalise_audio(extension, audio, get_ffmpeg_manager(self.hass).binary)
        return "wav", attenuate_wav(pcm, now=now)

    async def async_get_tts_audio(self, message, language, options):
        config = self._entry.options
        provider = config.get("primary_tts", DEFAULT_PROVIDER)
        if provider == self.entity_id or provider.startswith(_WRAPPERS):
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
                return await self._night_speech(await generate())
            if phrase_parts(message):
                whole = await self._cache.find_cached_audio(text=message, **identity)
                if whole:
                    return await self._night_speech(whole)
                try:
                    extension, audio, _, _ = await self._phrases.compose(message, identity, generate)
                    return await self._night_speech((extension, audio))
                except (ValueError, OSError, TimeoutError):
                    _LOGGER.warning("Phrase assembly unavailable; using whole-sentence TTS")
            extension, audio, _ = await self._cache.get_or_generate_audio(
                text=message, **identity, generate=generate,
            )
            return await self._night_speech((extension, audio))
        except Exception as err:  # noqa: BLE001 - any primary fault must reach REL-01 fallbacks
            # CancelledError is a BaseException and still propagates.
            _LOGGER.warning("Declan 2.0 TTS provider failed: %s", type(err).__name__)
        return await self._fallback_speech(message, language, config, provider, cache_enabled, identity)

    async def _fallback_speech(self, message, language, config, provider, cache_enabled, identity):
        """REL-01 steps after the primary voice failed; any fault ends in a clean error."""
        if cache_enabled and config.get("category_fallback", True):
            try:
                alternate = await self._cached_alternative(message, identity)
                if alternate is not None:
                    return await self._night_speech(alternate)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Declan 2.0 cached alternative unavailable: %s", type(err).__name__)
        local = await self._local_fallback(message, language, config, provider, cache_enabled)
        if local is not None:
            try:
                return await self._night_speech(local)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Declan 2.0 local TTS audio could not be prepared: %s", type(err).__name__)
        raise HomeAssistantError("Declan 2.0 could not generate speech") from None

    async def _local_fallback(self, message, language, config, primary, cache_enabled):
        """REL-01: speak with the local TTS entity when everything else failed."""
        provider = local_provider(config, primary, getattr(self, "entity_id", None))
        if provider is None:
            return None
        identity = {
            "provider": provider,
            "voice_id": f"{config.get('cache_revision', 'v1')}:local",
            "model": provider,
            "language": language or "en",
            "settings": {},
        }

        async def generate():
            text = spoken_text(message)
            await self._budget.reserve(text, "fallback")
            return await generate_from_existing_tts(
                self.hass, provider_entity_id=provider, text=text,
                language=language, options={},
            )

        try:
            if not cache_enabled:
                result = await generate()
            else:
                extension, audio, _ = await self._cache.get_or_generate_audio(
                    text=message, **identity, generate=generate,
                )
                result = (extension, audio)
        except Exception as err:  # noqa: BLE001 - third-party provider boundary
            _LOGGER.warning("Declan 2.0 local TTS fallback failed: %s", type(err).__name__)
            return None
        _LOGGER.info("Declan 2.0 spoke with the local TTS fallback")
        return result

    async def _cached_alternative(self, message, identity):
        try:
            catalogue = await self.hass.async_add_executor_job(
                load_catalogue, Path(__file__).with_name("responses.json"),
            )
        except (OSError, ValueError):
            return None

        # Guest wording only with the optional polite guest tone (FUT-60).
        guest = guest_tone(self.hass) == "polite" and guest_safe(self.hass, self._entry.options.get(
            "guest_mode_entity", DEFAULT_GUEST_MODE_ENTITY))
        alternatives = list(category_alternatives(message, catalogue, guest=guest))
        random.shuffle(alternatives)
        for alternate in alternatives:
            cached = await self._cache.find_cached_audio(text=alternate, **identity)
            if cached is not None:
                return cached
        return None
