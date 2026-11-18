"""Integrated Wyoming speaker-aware speech recognition, adapted from Jarvis-Voice-Bridge.

Accepts Wyoming speaker events before or shortly after Transcript.
"""
import asyncio
import logging
from collections.abc import AsyncIterable
from homeassistant.components import stt
from wyoming.client import AsyncTcpClient
from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioStart, AudioChunk, AudioStop
from wyoming.error import Error
from .speaker_models import (SpeakerMetadata, metadata_from_transcript,
                             transcript_for_ha, valid_wyoming_speaker)
from .capture_level import CaptureLevel
_LOGGER=logging.getLogger(__name__)

async def upload(client, stream, level):
    async for data in stream:
        level.add(data)
        await client.write_event(AudioChunk(rate=16000,width=2,channels=1,audio=data).event())
    level.finish()
    await client.write_event(AudioStop().event())

async def receive(client):
    identity = None
    speaker_event_seen = False
    speaker_unknown = False
    transcript = None
    speaker_arrived_after_transcript = False
    # Bound the wait after a transcript so missing speaker events cannot stall STT.
    late_speaker_timeout = 0.35
    late_speaker_deadline = None
    while True:
        try:
            if late_speaker_deadline is None:
                event = await client.read_event()
            else:
                remaining = late_speaker_deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                event = await asyncio.wait_for(client.read_event(), timeout=remaining)
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
            speaker_unknown = isinstance(name, str) and name.strip().casefold() in ('unknown', 'unidentified', 'none')
            valid = valid_wyoming_speaker(identity_id, name, confidence)
            if valid:
                identity = (identity_id, name, confidence)
            _LOGGER.info(
                "DECLAN_WYOMING_SPEAKER event=received valid=%s unknown=%s",
                valid, speaker_unknown,
            )
            if transcript is not None and valid:
                break
        elif Transcript.is_type(event.type):
            # Preserve the first command while waiting for late speaker identity.
            if transcript is not None:
                continue
            candidate = Transcript.from_event(event).text
            if not isinstance(candidate, str) or not candidate.strip():
                _LOGGER.info("DECLAN_WYOMING_SPEAKER event=empty_transcript")
                return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
            transcript = candidate
            if late_speaker_deadline is None:
                late_speaker_deadline = asyncio.get_running_loop().time() + late_speaker_timeout
            if identity is not None:
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
            transcript_for_ha(transcript, SpeakerMetadata(identity, None)),
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
                level = CaptureLevel()
                upload_task = asyncio.create_task(upload(client, stream, level))
                receive_task = asyncio.create_task(receive(client))
                try:
                    done, _ = await asyncio.wait(
                        (upload_task, receive_task), return_when=asyncio.FIRST_COMPLETED,
                    )
                    if upload_task in done:
                        upload_task.result()
                    result = await receive_task
                    text = getattr(result, "text", None)
                    if result.result == stt.SpeechResultState.SUCCESS and isinstance(text, str):
                        speaker = metadata_from_transcript(text).speaker
                        return stt.SpeechResult(
                            transcript_for_ha(text, SpeakerMetadata(speaker, level.snapshot())),
                            stt.SpeechResultState.SUCCESS,
                        )
                    return result
                finally:
                    upload_task.cancel()
                    receive_task.cancel()
                    await asyncio.gather(upload_task, receive_task, return_exceptions=True)
        except (OSError, TimeoutError, ValueError):
            _LOGGER.warning("Declan 2.0 Wyoming speech request could not complete")
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
