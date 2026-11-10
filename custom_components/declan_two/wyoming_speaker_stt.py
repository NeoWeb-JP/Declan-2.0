"""Integrated Wyoming speaker-aware speech recognition, adapted from Jarvis-Voice-Bridge.

Accepts Wyoming speaker events before or shortly after Transcript.
"""
import asyncio
import logging
import math
from collections.abc import AsyncIterable
from homeassistant.components import stt
from wyoming.client import AsyncTcpClient
from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioStart, AudioChunk, AudioStop
from wyoming.error import Error
from .speaker_models import SpeakerTranscript
_LOGGER=logging.getLogger(__name__)

async def upload(client, stream):
    async for data in stream:
        await client.write_event(AudioChunk(rate=16000,width=2,channels=1,audio=data).event())
    await client.write_event(AudioStop().event())

async def receive(client):
    identity = None
    speaker_event_seen = False
    speaker_unknown = False
    transcript = None
    speaker_arrived_after_transcript = False
    # Bound the wait after a transcript so missing speaker events cannot stall STT.
    late_speaker_timeout = 0.35
    while True:
        try:
            event = (
                await asyncio.wait_for(client.read_event(), timeout=late_speaker_timeout)
                if transcript is not None else await client.read_event()
            )
        except asyncio.TimeoutError:
            break
        if event is None:
            break
        if event.type == 'jarvis-speaker':
            speaker_arrived_after_transcript = transcript is not None
            speaker_event_seen = True
            value = event.data if isinstance(event.data, dict) else {}
            name = value.get('speaker')
            confidence = value.get('confidence')
            identity_id = value.get('interaction_id')
            speaker_unknown = isinstance(name, str) and name.casefold() in ('unknown', 'unidentified', 'none')
            valid = (
                isinstance(name, str) and bool(name) and len(name) <= 80
                and isinstance(identity_id, str) and len(identity_id) <= 80
                and isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
                and math.isfinite(confidence) and 0 <= confidence <= 1
            )
            if valid and not speaker_unknown:
                identity = (identity_id, name, confidence)
            _LOGGER.info(
                "DECLAN_WYOMING_SPEAKER event=received valid=%s unknown=%s",
                valid, speaker_unknown,
            )
            if transcript is not None:
                break
        elif Transcript.is_type(event.type):
            transcript = Transcript.from_event(event).text
            if speaker_event_seen:
                break
        elif Error.is_type(event.type):
            _LOGGER.info(
                "DECLAN_WYOMING_SPEAKER event=error speaker_event_seen=%s",
                speaker_event_seen,
            )
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
    if transcript is not None:
        _LOGGER.info(
            "DECLAN_WYOMING_SPEAKER event=transcript speaker_event_seen=%s "
            "identity_attached=%s ordering=%s",
            speaker_event_seen, identity is not None,
            ('speaker_after_transcript' if speaker_arrived_after_transcript
             else 'speaker_before_transcript' if speaker_event_seen
             else 'speaker_missing'),
        )
        return stt.SpeechResult(
            SpeakerTranscript(transcript, identity),
            stt.SpeechResultState.SUCCESS,
        )
    _LOGGER.info(
        "DECLAN_WYOMING_SPEAKER event=stream_closed speaker_event_seen=%s",
        speaker_event_seen,
    )
    return stt.SpeechResult(None, stt.SpeechResultState.ERROR)

class DeclanWyomingVoiceBridge(stt.SpeechToTextEntity):
    _attr_name = "Declan 2.0 Wyoming Speaker Recognition"

    def __init__(self, entry):
        self.host = entry.options["wyoming_bridge_host"]
        self.port = entry.options.get("wyoming_bridge_port", 10300)
        self._attr_unique_id = f"{entry.entry_id}_wyoming_speaker_stt"

    @property
    def supported_languages(self):
        return ["en"]

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

    async def async_process_audio_stream(self, metadata, stream: AsyncIterable[bytes]):
        try:
            async with asyncio.timeout(85), AsyncTcpClient(self.host, self.port) as client:
                await client.write_event(Transcribe(language=metadata.language).event())
                await client.write_event(AudioStart(rate=16000, width=2, channels=1).event())
                upload_task = asyncio.create_task(upload(client, stream))
                receive_task = asyncio.create_task(receive(client))
                try:
                    done, _ = await asyncio.wait(
                        (upload_task, receive_task), return_when=asyncio.FIRST_COMPLETED,
                    )
                    if upload_task in done:
                        upload_task.result()
                    return await receive_task
                finally:
                    upload_task.cancel()
                    receive_task.cancel()
                    await asyncio.gather(upload_task, receive_task, return_exceptions=True)
        except (OSError, TimeoutError, ValueError):
            _LOGGER.warning("Declan 2.0 Wyoming speech request could not complete")
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
