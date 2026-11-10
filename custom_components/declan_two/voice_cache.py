"""Provider-independent, persistent cache for synthesized Declan speech.

No Home Assistant or ElevenLabs dependency. The TTS platform will call
get_or_generate with bytes returned by its configured speech provider.
Do not include secrets or personal speaker profiles in the cache metadata.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import shutil
from time import time
from typing import Awaitable, Callable


class VoiceCache:
    """Cache by exact spoken text and voice generation parameters."""

    def __init__(self, directory: str | Path, *, max_bytes=256*1024*1024,
                 min_free_bytes=512*1024*1024) -> None:
        self.directory = Path(directory)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.hits = 0
        self.misses = 0
        self.max_bytes = max_bytes
        self.min_free_bytes = min_free_bytes
        self.skipped_writes = 0
        self._write_lock = asyncio.Lock()

    async def _save(self, path, audio, metadata):
        """Bound all new writes, including concurrent different phrases."""
        async with self._write_lock:
            def write():
                self.directory.mkdir(parents=True, exist_ok=True)
                used = sum(p.stat().st_size for p in self.directory.rglob('*') if p.is_file())
                sidecar = path.with_suffix(path.suffix+'.json')
                encoded = json.dumps(metadata, ensure_ascii=False).encode('utf-8')
                required = len(audio)+len(encoded)
                if used+required > self.max_bytes or shutil.disk_usage(self.directory).free-required < self.min_free_bytes:
                    return False
                path.parent.mkdir(parents=True, exist_ok=True)
                for target, content in [(path, audio), (sidecar, encoded)]:
                    fd, tmp = tempfile.mkstemp(prefix='.jarvis-', dir=path.parent)
                    try:
                        with os.fdopen(fd, 'wb') as stream:
                            stream.write(content)
                            stream.flush()
                            os.fsync(stream.fileno())
                        os.replace(tmp, target)
                    finally:
                        if os.path.exists(tmp):os.unlink(tmp)
                return True
            if not await asyncio.to_thread(write):
                self.skipped_writes += 1
                return False
            return True

    async def snapshot(self, limit=200, query='', page=None, page_size=10):
        """Private administrator inventory; old files remain readable."""
        if not isinstance(query,str) or len(query)>200:
            raise ValueError('Search must be at most 200 characters')
        query=query.strip().casefold()
        if page is not None and (type(page) is not int or page < 1):
            raise ValueError('Page must be a positive integer')
        if type(page_size) is not int or not 1 <= page_size <= 100:
            raise ValueError('Invalid page size')
        def scan():
            parent = self.directory
            while not parent.exists():parent = parent.parent
            free = shutil.disk_usage(parent).free
            entries=[]; used=0; count=0
            for path in self.directory.glob('*/*'):
                if not path.is_file() or path.is_symlink():continue
                used += path.stat().st_size
                if path.suffix[1:] not in {'wav','mp3','ogg','flac'}:continue
                count += 1
                try:
                    metadata=json.loads(path.with_suffix(path.suffix+'.json').read_text(encoding='utf-8'))
                    if not isinstance(metadata,dict):raise ValueError('Invalid metadata')
                except (OSError,ValueError):
                    metadata={'text':'Older cached audio (text unavailable)','kind':'legacy'}
                entries.append({**metadata,'key':path.stem,'extension':path.suffix[1:],
                                'bytes':path.stat().st_size})
            entries.sort(key=lambda item:(item.get('created',0),item['key']),reverse=True)
            matches=[entry for entry in entries if not query or query in ' '.join(
                str(entry.get(field,'')) for field in ('text','kind','provider','voice_id')
            ).casefold()]
            page_count=max(1,(len(matches)+page_size-1)//page_size)
            current_page=min(page,page_count) if page is not None else 1
            offset=(current_page-1)*page_size
            shown=matches[offset:offset+page_size] if page is not None else matches[:limit]
            return {'entries':shown, 'palette_entries':entries[:limit],
                    'page':current_page,'page_count':page_count,'page_size':page_size,
                    'first':offset+1 if shown else 0,'last':offset+len(shown),
                    'matched_count':len(matches), 'query':query, 'count':count, 'bytes':used,
                    'limit_bytes':self.max_bytes, 'free_bytes':free,
                    'reserve_bytes':self.min_free_bytes,
                    'storage_available':used < self.max_bytes and free > self.min_free_bytes,
                    'hits':self.hits,'misses':self.misses,'skipped_writes':self.skipped_writes}
        return await asyncio.to_thread(scan)

    async def saved_audio(self, key, extension):
        path=self.path_for(key,extension)
        def read():
            if path.is_symlink() or path.parent.is_symlink():raise ValueError('Invalid cache path')
            if path.stat().st_size > 8*1024*1024:raise ValueError('Audio too large to preview')
            return path.read_bytes()
        return await asyncio.to_thread(read)

    @staticmethod
    def key(*, text: str, provider: str, voice_id: str, model: str,
            language: str = "en", settings: dict | None = None,
            extension: str = "wav") -> str:
        """Content-addressed key; exclude credentials and volatile metadata."""
        if extension not in {"wav", "mp3", "ogg", "flac"}:
            raise ValueError("Unsupported audio format")
        payload = {
            "text": text, "provider": provider, "voice_id": voice_id,
            "model": model, "language": language, "settings": settings or {},
            "extension": extension, "cache_version": 1,
        }
        serialised = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                ensure_ascii=False, allow_nan=False)
        return sha256(serialised.encode("utf-8")).hexdigest()

    def path_for(self, key: str, extension: str = "wav") -> Path:
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("Invalid cache key")
        if extension not in {"wav", "mp3", "ogg", "flac"}:
            raise ValueError("Unsupported audio format")
        return self.directory / key[:2] / f"{key}.{extension}"

    async def get_or_generate(
        self,
        *,
        text: str,
        provider: str,
        voice_id: str,
        model: str,
        generate: Callable[[], Awaitable[bytes]],
        language: str = "en",
        settings: dict | None = None,
        extension: str = "wav",
    ) -> tuple[bytes, bool]:
        """Return (audio, cache_hit); coalesce concurrent identical requests.

        Provider failure is propagated to the caller, which may use XTTS.
        A fallback voice must use its OWN provider/voice key.
        """
        key = self.key(text=text, provider=provider, voice_id=voice_id,
                       model=model, language=language, settings=settings,
                       extension=extension)
        path = self.path_for(key, extension)
        async with self._locks[key]:
            try:
                audio = await asyncio.to_thread(path.read_bytes)
                if audio:
                    self.hits += 1
                    return audio, True
            except FileNotFoundError:
                pass

            # Never cache failed or empty generations.
            audio = await generate()
            if not isinstance(audio, bytes) or not audio:
                raise ValueError("TTS provider returned empty or invalid audio")

            await self._save(path, audio, dict(text=text, provider=provider,
                voice_id=voice_id, kind="sentence", created=time()))
            self.misses += 1
            return audio, False

    async def get_or_generate_audio(
        self, *, text: str, provider: str, voice_id: str, model: str,
        generate: Callable[[], Awaitable[tuple[str, bytes]]],
        language: str = "en", settings: dict | None = None, kind="sentence",
    ) -> tuple[str, bytes, bool]:
        """Cache audio when the provider chooses its output format.

        An identity-wide lock prevents simultaneous misses from generating
        multiple paid requests. Never return a different provider's audio.
        """
        identity = self.key(
            text=text, provider=provider, voice_id=voice_id, model=model,
            language=language, settings=settings, extension="wav"
        )
        async with self._locks[identity]:
            for ext in ("mp3", "wav", "ogg", "flac"):
                key = self.key(
                    text=text, provider=provider, voice_id=voice_id,
                    model=model, language=language, settings=settings,
                    extension=ext
                )
                path = self.path_for(key, ext)
                try:
                    audio = await asyncio.to_thread(path.read_bytes)
                    if audio:
                        self.hits += 1
                        return ext, audio, True
                except FileNotFoundError:
                    pass

            ext, audio = await generate()
            if ext not in {"mp3", "wav", "ogg", "flac"}:
                raise ValueError("Unsupported TTS audio format")
            if not isinstance(audio, bytes) or not audio:
                raise ValueError("TTS provider returned empty or invalid audio")
            key = self.key(
                text=text, provider=provider, voice_id=voice_id, model=model,
                language=language, settings=settings, extension=ext
            )
            path = self.path_for(key, ext)

            await self._save(path, audio, dict(text=text, provider=provider,
                voice_id=voice_id, kind=kind, created=time()))
            self.misses += 1
            return ext, audio, False

    async def find_cached_audio(
        self, *, text: str, provider: str, voice_id: str, model: str,
        language: str = "en", settings: dict | None = None,
    ) -> tuple[str, bytes] | None:
        """Read ONLY an existing recording without invoking a TTS provider."""
        for ext in ("mp3", "wav", "ogg", "flac"):
            key = self.key(
                text=text, provider=provider, voice_id=voice_id, model=model,
                language=language, settings=settings, extension=ext,
            )
            try:
                audio = await asyncio.to_thread(self.path_for(key, ext).read_bytes)
            except FileNotFoundError:
                continue
            if audio:
                self.hits += 1
                return ext, audio
        return None

    async def store_audio(
        self, *, text: str, provider: str, voice_id: str, model: str,
        extension: str, audio: bytes, language: str = "en",
        settings: dict | None = None, kind: str = 'sentence', parts=None, gap_ms=None,
    ) -> bool:
        """Replace a saved recording with newly generated provider audio."""
        if extension not in {"mp3", "wav", "ogg", "flac"}:
            raise ValueError("Unsupported TTS audio format")
        if not isinstance(audio, bytes) or not audio:
            raise ValueError("TTS provider returned empty or invalid audio")
        identity = self.key(
            text=text, provider=provider, voice_id=voice_id, model=model,
            language=language, settings=settings, extension="wav",
        )
        key = self.key(
            text=text, provider=provider, voice_id=voice_id, model=model,
            language=language, settings=settings, extension=extension,
        )
        path = self.path_for(key, extension)
        async with self._locks[identity]:
            metadata=dict(text=text,provider=provider,voice_id=voice_id,kind=kind,created=time())
            if parts is not None:
                metadata.update(parts=parts,gap_ms=gap_ms)
            saved=await self._save(path,audio,metadata)
            if saved:
                def remove_older_formats():
                    for ext in {'wav','mp3','ogg','flac'}-{extension}:
                        old_key=self.key(text=text,provider=provider,voice_id=voice_id,model=model,
                                         language=language,settings=settings,extension=ext)
                        old_path=self.path_for(old_key,ext)
                        old_path.unlink(missing_ok=True)
                        old_path.with_suffix('.'+ext+'.json').unlink(missing_ok=True)
                await asyncio.to_thread(remove_older_formats)
            self.misses += 1
            return saved
