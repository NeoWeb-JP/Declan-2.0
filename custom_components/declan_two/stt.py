"""Optional OpenAI speech-to-text entity for Declan Assist pipelines."""
from __future__ import annotations

import io
import logging
import wave

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
    """Only expose cloud STT after an API key is explicitly configured."""
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
        try:
            async for chunk in stream:
                raw.extend(chunk)
                if len(raw) > MAX_AUDIO_BYTES:
                    _LOGGER.warning("Declan OpenAI STT rejected oversized utterance")
                    return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
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
            timeout = aiohttp.ClientTimeout(total=25)
            session = async_get_clientsession(self.hass)
            async with session.post(ENDPOINT, data=form, headers=headers, timeout=timeout, allow_redirects=False) as response:
                if response.status != 200:
                    _LOGGER.warning("Declan OpenAI STT request failed (HTTP %s)", response.status)
                    return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
                payload = await response.json()
            text = payload.get("text") if isinstance(payload, dict) else None
            text = text.strip() if isinstance(text, str) else ""
            if not text:
                return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
            return stt.SpeechResult(text, stt.SpeechResultState.SUCCESS)
        except (aiohttp.ClientError, TimeoutError, ValueError, KeyError):
            _LOGGER.warning("Declan OpenAI STT request could not complete")
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
