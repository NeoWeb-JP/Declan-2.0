"""Exact music-response templates and reusable, voice-isolated PCM clips."""
from __future__ import annotations

import asyncio
import io
import re
import wave
from array import array
import sys

RATE = 24000
MAX_SECONDS = 30
ASSEMBLY_VERSION = "phrases-pcm-v1"


def phrase_parts(message: str) -> list[str] | None:
    """Preserve wording exactly; never rewrite arbitrary responses or errors."""
    slot = r"([\w][\w '&’+/-]{0,79})"
    patterns = [
        r"(Playing )" + slot + r"( music from Spotify in the )" + slot + r"(\.)",
        r"(I requested )" + slot + r"( in )" + slot + r"(\.)",
        r"(I’ve requested )" + slot + r"( music from Spotify in the )" + slot + r"(\.)",
    ]
    for pattern in patterns:
        match = re.fullmatch(pattern, message)
        if match:
            # Attach final punctuation to the room for sentence-final intonation.
            return [match[1].strip(), match[2], match[3].strip(), match[4]+match[5]]
    return None


def pcm_wave(pcm: bytes) -> bytes:
    if not pcm or len(pcm) % 2:
        raise ValueError("Invalid PCM audio")
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(RATE)
        stream.writeframes(pcm)
    return output.getvalue()


def read_pcm(audio: bytes) -> bytes:
    with wave.open(io.BytesIO(audio), "rb") as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype()) != (1, 2, RATE, "NONE"):
            raise ValueError("Clip format does not match phrase library")
        if not 0 < stream.getnframes() <= RATE * MAX_SECONDS:
            raise ValueError("Clip is empty or too long")
        pcm = stream.readframes(stream.getnframes())
        if len(pcm) != stream.getnframes()*2:
            raise ValueError("Truncated audio clip")
        return pcm


async def normalise_audio(extension: str, audio: bytes, binary: str = "ffmpeg") -> bytes:
    """Decode each clip once, so MP3 headers/delays are never concatenated."""
    if extension == "wav":
        try:
            read_pcm(audio)
            return audio
        except (ValueError, wave.Error, EOFError):
            pass
    if extension not in {"wav", "mp3", "ogg", "flac"} or not audio or len(audio) > 8*1024*1024:
        raise ValueError("Invalid speech audio")
    process = await asyncio.create_subprocess_exec(
        binary, "-hide_banner", "-loglevel", "error", "-nostdin",
        "-protocol_whitelist", "pipe", "-i", "pipe:0", "-vn",
        "-t", str(MAX_SECONDS+1), "-ac", "1", "-ar", str(RATE),
        "-f", "s16le", "pipe:1",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        pcm, _ = await asyncio.wait_for(process.communicate(audio), timeout=20)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    if process.returncode or not pcm or len(pcm) > RATE*MAX_SECONDS*2:
        raise ValueError("Speech clip could not be decoded or is too long")
    return pcm_wave(pcm)


def join_clips(clips: list[bytes], gap_ms: int = 20) -> bytes:
    """Build one WAV with a short word boundary, never separate play calls."""
    if not 1 <= len(clips) <= 8:
        raise ValueError("Invalid clip count")
    if type(gap_ms) is not int or not 0 <= gap_ms <= 500:
        raise ValueError('Pause must be between 0 and 500 milliseconds')
    parts = []
    for audio in clips:
        samples=array('h',read_pcm(audio))
        if sys.byteorder != 'little':samples.byteswap()
        start=0;end=len(samples)
        while start < end and abs(samples[start]) <= 64:start+=1
        while end > start and abs(samples[end-1]) <= 64:end-=1
        if start == end:raise ValueError('Speech clip contains only silence')
        # Keep a small edge margin, removing only leading/trailing near-silence.
        trimmed=samples[max(0,start-RATE//100):min(len(samples),end+RATE//100)]
        if sys.byteorder != 'little':trimmed.byteswap()
        parts.append(trimmed.tobytes())
    silence = b"\0\0" * (RATE * gap_ms // 1000)
    pcm = silence.join(parts)
    if len(pcm) > RATE*MAX_SECONDS*2:
        raise ValueError("Combined response is too long")
    return pcm_wave(pcm)


class PhraseLibrary:
    def __init__(self, cache, normalise=normalise_audio):
        self.cache = cache
        self.normalise = normalise

    @staticmethod
    def clip_identity(identity):
        return {**identity, 'model':identity['model']+':'+ASSEMBLY_VERSION+':clip'}

    @staticmethod
    def validate_sentence(parts, gap_ms):
        if not isinstance(parts,list) or not 1 <= len(parts) <= 8:
            raise ValueError('Choose between 1 and 8 clips')
        if type(gap_ms) is not int or not 0 <= gap_ms <= 500:
            raise ValueError('Pause must be between 0 and 500 milliseconds')
        if any(not isinstance(p,str) or not 1 <= len(p.strip()) <= 200 for p in parts):
            raise ValueError('Invalid clip text')

    async def save_sentence(self, parts, identity, generate, gap_ms=20):
        """Generate only missing clips, then save exact text for normal TTS reuse."""
        self.validate_sentence(parts,gap_ms)
        state=await self.cache.snapshot(limit=0)
        if not state['storage_available']:
            raise ValueError('Cache storage is full; no generation requested')
        clips=[];generated=0
        for part in parts:
            _,audio,hit=await self.clip(part,identity,generate)
            generated+=not hit
            clips.append(audio)
        audio=join_clips(clips,gap_ms)
        text=' '.join(part.strip() for part in parts)
        saved=await self.cache.store_audio(text=text,**identity,extension='wav',audio=audio,
                                          kind='built_sentence',parts=[p.strip() for p in parts],gap_ms=gap_ms)
        return {'text':text,'saved':saved,'generated_clips':generated,
                'reused_clips':len(parts)-generated,'bytes':len(audio)}

    async def preview(self, parts, identity, gap_ms=20):
        """Read-only composition: no providers, persistence or household actions."""
        self.validate_sentence(parts,gap_ms)
        clips=[];missing=[]
        for part in parts:
            text=part.strip().casefold()
            saved=await self.cache.find_cached_audio(text=text,**self.clip_identity(identity))
            if saved is None:
                if text not in missing:missing.append(text)
            else:
                extension,audio=saved
                if extension != 'wav':raise ValueError('Reimport that clip as a reusable recording')
                clips.append(audio)
        if missing:return {'missing':missing}
        return {'missing':[], 'audio':join_clips(clips,gap_ms), 'extension':'wav'}

    async def import_clips(self, clips, identity):
        """Validate every clip before saving. Existing keys are preserved."""
        prepared=[]
        clip_identity=self.clip_identity(identity)
        for text,extension,audio in clips:
            converted=join_clips([await self.normalise(extension,audio)])
            prepared.append((text,converted))
        required=sum(len(audio)+2048 for _,audio in prepared)
        state=await self.cache.snapshot(limit=0)
        if state['bytes']+required > state['limit_bytes'] or state['free_bytes']-required < state['reserve_bytes']:
            raise ValueError('Not enough cache space to import these recordings')
        imported=[];existing=[];not_saved=[]
        for text,audio in prepared:
            async def generate(audio=audio):return 'wav',audio
            try:
                _,_,hit=await self.cache.get_or_generate_audio(
                    text=text,**clip_identity,generate=generate,kind='imported_clip',
                )
                key=self.cache.key(text=text,**clip_identity,extension='wav')
                saved=await asyncio.to_thread(self.cache.path_for(key,'wav').is_file)
            except OSError:
                not_saved.append(text)
                continue
            # A concurrent write can consume the remaining budget; report it.
            if not saved:not_saved.append(text)
            elif hit:existing.append(text)
            else:imported.append(text)
        return {'imported':imported,'existing':existing,'not_saved':not_saved}

    async def clip(self, text, identity, generate):
        text=text.strip().casefold()
        clip_identity = self.clip_identity(identity)
        async def create():
            extension, audio = await generate(text)
            converted = await self.normalise(extension, audio)
            # Validate and trim before saving; never persist silent/broken clips.
            return "wav", join_clips([converted])
        return await self.cache.get_or_generate_audio(
            text=text, **clip_identity, generate=create, kind="clip",
        )

    async def compose(self, message, identity, generate):
        parts = phrase_parts(message)
        if parts is None:
            return None
        composed_identity = {**identity, "model": identity["model"]+":"+ASSEMBLY_VERSION+":sentence"}
        generated = 0
        async def create():
            nonlocal generated
            clips = []
            for part in parts:
                _, audio, hit = await self.clip(part, identity, generate)
                generated += not hit
                clips.append(audio)
            return "wav", join_clips(clips)
        extension, audio, hit = await self.cache.get_or_generate_audio(
            text=message, **composed_identity, generate=create, kind="assembled",
        )
        return extension, audio, hit, generated







