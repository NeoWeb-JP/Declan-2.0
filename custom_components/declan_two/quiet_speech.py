"""Apply night-time speech attenuation to audio, not media-player volume.

The source player level is never changed, so Music Assistant streams are
unaffected and there is no volume state to restore after TTS.
"""
from datetime import datetime, time
from io import BytesIO
import wave
from array import array
import sys


def quiet_hours(now=None):
    clock = (now or datetime.now().astimezone()).time()
    return clock >= time(23) or clock < time(7)


def attenuate_wav(audio, *, now=None):
    """Scale 16-bit PCM speech samples to 20% during quiet hours."""
    if not quiet_hours(now):
        return audio
    with wave.open(BytesIO(audio), "rb") as source:
        params = source.getparams()
        if params.sampwidth != 2 or params.comptype != "NONE":
            raise ValueError("Quiet speech requires uncompressed 16-bit PCM")
        frames = source.readframes(params.nframes)
    samples = array("h")
    samples.frombytes(frames)
    if sys.byteorder != "little":
        samples.byteswap()
    for index, value in enumerate(samples):
        samples[index] = int(value * 0.2)
    if sys.byteorder != "little":
        samples.byteswap()
    result = BytesIO()
    with wave.open(result, "wb") as output:
        output.setparams(params)
        output.writeframes(samples.tobytes())
    return result.getvalue()
