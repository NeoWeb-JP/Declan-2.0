"""Optional OpenAI speech-to-text entity for Declan Assist pipelines."""
from __future__ import annotations

import io
import asyncio
import logging
import wave

from .capture_level import CaptureLevel
from .speaker_models import SpeakerTranscript

import aiohttp
from homeassistant.components import stt
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)
ENDPOINT = "https://api.openai.com/v1/audio/transcriptions"
MAX_AUDIO_BYTES = 16_000 * 2 * 60  # one minute of 16 kHz, 16-bit mono PCM
PROMPT = (
    "Home Assistant voice commands. Declan, Jaco, Edd, fairy lights, "
    "dining room, kitchen spotlights, sexy time, braai music, Spotify."
)


def pcm_to_wav(raw: bytes, *, sample_rate: int = 16000) -> bytes:
    """Wrap mono signed 16-bit PCM in a WAV container for the API."""
    with io.BytesIO() as buffer:
        with wave.open(buffer, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            output.writeframes(raw)
        return buffer.getvalue()


async def async_setup_entry(hass, entry, async_add_entities):
    """Expose the configured speech engines independently."""
    if entry.options.get("wyoming_bridge_enabled") and entry.options.get("wyoming_bridge_host"):
        from .wyoming_speaker_stt import DeclanWyomingVoiceBridge

        async_add_entities([DeclanWyomingVoiceBridge(entry)])
    if entry.options.get("openai_stt_enabled") and entry.options.get("openai_stt_api_key"):
        async_add_entities([DeclanOpenAISTT(hass, entry)])


class DeclanOpenAISTT(stt.SpeechToTextEntity):
    _attr_name = "Declan 2.0 OpenAI Transcription"

    def __init__(self, hass, entry):
        self._attr_unique_id = f"{entry.entry_id}_openai_stt"
        self.hass = hass
        self.entry = entry

    @property
    def supported_languages(self):
        return ["en", "en-GB", "en-US", "en-ZA"]

    @property
    def supported_formats(self):
        return [stt.AudioFormats.WAV]

    @property
    def supported_codecs(self):
        return [stt.AudioCodecs.PCM]

    @property
    def supported_bit_rates(self):
        return [stt.AudioBitRates.BITRATE_16]

    @property
    def supported_sample_rates(self):
        return [stt.AudioSampleRates.SAMPLERATE_16000]

    @property
    def supported_channels(self):
        return [stt.AudioChannels.CHANNEL_MONO]

    async def async_process_audio_stream(self, metadata, stream):
        """Send one bounded Assist utterance to OpenAI; never log audio or key."""
        raw = bytearray()
        level = CaptureLevel()
        try:
            async for chunk in stream:
                raw.extend(chunk)
                level.add(chunk)
                if len(raw) > MAX_AUDIO_BYTES:
                    _LOGGER.warning("Declan OpenAI STT rejected oversized utterance")
                    return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
            level.finish()
            if not raw:
                return stt.SpeechResult(None, stt.SpeechResultState.ERROR)

            options = self.entry.options
            form = aiohttp.FormData()
            form.add_field("file", pcm_to_wav(bytes(raw)),
                           filename="utterance.wav", content_type="audio/wav")
            form.add_field("model", options.get("openai_stt_model", "gpt-transcribe"))
            form.add_field("language", "en")
            form.add_field("prompt", PROMPT)
            form.add_field("response_format", "json")
            headers = {"Authorization": "Bearer " + options["openai_stt_api_key"]}
            timeout = aiohttp.ClientTimeout(total=8, sock_connect=3)
            session = async_get_clientsession(self.hass)
            async with session.post(ENDPOINT, data=form, headers=headers, timeout=timeout, allow_redirects=False) as response:
                if response.status != 200:
                    _LOGGER.warning("Declan OpenAI STT request failed (HTTP %s)", response.status)
                    raise ValueError('Cloud transcription failed')
                payload = await response.json()
            text = payload.get("text") if isinstance(payload, dict) else None
            text = text.strip() if isinstance(text, str) else ""
            if not text:
                raise ValueError('Cloud transcription was empty')
            return stt.SpeechResult(SpeakerTranscript(text, capture_level=level.snapshot()), stt.SpeechResultState.SUCCESS)
        except (aiohttp.ClientError, TimeoutError, ValueError, KeyError):
            _LOGGER.warning("Declan OpenAI STT request could not complete")
            if raw and len(raw) <= MAX_AUDIO_BYTES and level.snapshot() is not None:
                return await self._fallback(metadata, bytes(raw), level.snapshot())
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)

    async def _fallback(self, metadata, raw, capture):
        """Replay bounded PCM once to the configured local provider."""
        try:
            return await self._run_fallback(metadata, raw, capture)
        except (OSError, TimeoutError, ValueError, AttributeError, aiohttp.ClientError):
            _LOGGER.warning('Declan local STT fallback could not complete')
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)

    async def _run_fallback(self, metadata, raw, capture):
        options = self.entry.options
        engine = None
        entity_id = options.get('local_stt_entity', '').strip()
        if entity_id:
            engine = stt.async_get_speech_to_text_entity(self.hass, entity_id)
            if engine is self or isinstance(engine, DeclanOpenAISTT):
                engine = None
        elif options.get('wyoming_bridge_enabled') and options.get('wyoming_bridge_host'):
            from .wyoming_speaker_stt import DeclanWyomingVoiceBridge
            engine = DeclanWyomingVoiceBridge(self.entry)
        if engine is None:
            _LOGGER.warning('Declan local STT fallback is not available')
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)

        async def replay():
            for offset in range(0, len(raw), 4096):
                yield raw[offset:offset + 4096]
        try:
            async with asyncio.timeout(12):
                if not engine.check_metadata(metadata):
                    return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
                result = await engine.async_process_audio_stream(metadata, replay())
            if result.result == stt.SpeechResultState.SUCCESS and isinstance(result.text, str) and result.text.strip():
                text = SpeakerTranscript(result.text, getattr(result.text, 'jarvis_speaker', None), capture_level=capture)
                return stt.SpeechResult(text, stt.SpeechResultState.SUCCESS)
        except (OSError, TimeoutError, ValueError, aiohttp.ClientError):
            _LOGGER.warning('Declan local STT fallback could not complete')
        return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
