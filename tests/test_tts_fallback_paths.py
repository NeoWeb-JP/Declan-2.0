"""TTS failures of any kind must reach the cached alternative and local
fallback, end in a clean HomeAssistantError, and never waste paid audio."""
import errno
from importlib import import_module
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import test_assist_bridge as bridge_harness

IDENTITY = {"provider": "tts.elevenlabs", "voice_id": "declan-v1", "model": "multilingual-v2"}


class TTSFallbackPathTests(IsolatedAsyncioTestCase):
    setUp = bridge_harness.AssistBridgeTests.setUp
    _voice_manager = bridge_harness.AssistBridgeTests._voice_manager

    async def test_unexpected_primary_errors_still_reach_local_tts(self):
        for failure in (RuntimeError("provider crashed"), KeyError("voice"), AttributeError("hass")):
            with self.subTest(failure=type(failure).__name__):
                platform, entity, _, budget = self._voice_manager(
                    {"tts_enabled": True, "local_tts": "tts.piper"})

                async def provider(hass, *, provider_entity_id, **kwargs):
                    if provider_entity_id == "tts.piper":
                        return "wav", b"local"
                    raise failure
                with patch.object(platform, "quiet_hours", return_value=False), \
                        patch.object(platform, "generate_from_existing_tts", AsyncMock(side_effect=provider)), \
                        patch.object(entity, "_cached_alternative", AsyncMock(return_value=None)), \
                        self.assertLogs(platform._LOGGER, "WARNING") as logs:
                    self.assertEqual(await entity.async_get_tts_audio("Hello", "en", {}), ("wav", b"local"))
                self.assertIn(type(failure).__name__, "\n".join(logs.output))
                self.assertEqual(budget.reserve.await_args_list[-1].args, ("Hello", "fallback"))

    async def test_faulty_local_tts_or_alternative_lookup_ends_in_clean_error(self):
        platform, entity, _, _ = self._voice_manager({"tts_enabled": True, "local_tts": "tts.piper"})
        with patch.object(platform, "quiet_hours", return_value=False), \
                patch.object(platform, "generate_from_existing_tts",
                             AsyncMock(side_effect=RuntimeError("everything is down"))), \
                patch.object(entity, "_cached_alternative", AsyncMock(side_effect=PermissionError("cache"))), \
                self.assertRaises(platform.HomeAssistantError):
            await entity.async_get_tts_audio("Hello", "en", {})

    async def test_alternative_lookup_failure_still_tries_local_tts(self):
        platform, entity, _, _ = self._voice_manager({"tts_enabled": True, "local_tts": "tts.piper"})

        async def provider(hass, *, provider_entity_id, **kwargs):
            if provider_entity_id == "tts.piper":
                return "wav", b"local"
            raise platform.HomeAssistantError("down")
        with patch.object(platform, "quiet_hours", return_value=False), \
                patch.object(platform, "generate_from_existing_tts", AsyncMock(side_effect=provider)), \
                patch.object(entity, "_cached_alternative", AsyncMock(side_effect=PermissionError("cache"))):
            self.assertEqual(await entity.async_get_tts_audio("Hello", "en", {}), ("wav", b"local"))

    async def test_quiet_hours_ffmpeg_failure_ends_in_clean_error(self):
        platform, entity, _, _ = self._voice_manager({"tts_enabled": True, "local_tts": "tts.piper"})
        with patch.object(platform, "generate_from_existing_tts", AsyncMock(return_value=("mp3", b"audio"))), \
                patch.object(entity, "_night_speech", AsyncMock(side_effect=RuntimeError("ffmpeg exited 1"))), \
                patch.object(entity, "_cached_alternative", AsyncMock(return_value=None)), \
                self.assertRaises(platform.HomeAssistantError):
            await entity.async_get_tts_audio("Hello", "en", {})


class VoiceCacheFailureTests(IsolatedAsyncioTestCase):
    """Cache faults are a miss or a skipped write, never a lost paid request."""

    def setUp(self):
        package = ModuleType("declan_tts_fallback_tests")
        package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components/declan_two")]
        self.enterContext(patch.dict(sys.modules, {package.__name__: package}))
        self.cache_module = import_module(package.__name__ + ".voice_cache")
        self.directory = Path(self.enterContext(TemporaryDirectory())) / "cache"
        self.cache = self.cache_module.VoiceCache(self.directory, min_free_bytes=0)

    def _block(self, text, extension):
        """Make the cached path unreadable (a directory where a file should be)."""
        key = self.cache.key(text=text, **IDENTITY, extension=extension)
        path = self.cache.path_for(key, extension)
        path.mkdir(parents=True)
        return path

    async def test_unreadable_cache_entry_is_a_miss_and_is_regenerated(self):
        self._block("Hello", "mp3")
        generate = AsyncMock(return_value=("wav", b"fresh"))
        self.assertEqual(await self.cache.get_or_generate_audio(text="Hello", **IDENTITY, generate=generate),
                         ("wav", b"fresh", False))
        generate.assert_awaited_once()
        # Fixed-format and lookup-only paths treat it as a miss too.
        self._block("Fixed", "wav")
        self.assertEqual(await self.cache.get_or_generate(text="Fixed", **IDENTITY,
                                                          generate=AsyncMock(return_value=b"pcm")),
                         (b"pcm", False))
        self._block("Lookup", "mp3")
        self.assertIsNone(await self.cache.find_cached_audio(text="Lookup", **IDENTITY))

    async def test_failed_cache_write_still_returns_paid_audio(self):
        generate = AsyncMock(return_value=("mp3", b"paid audio"))
        no_space = OSError(errno.ENOSPC, "No space left on device")
        with patch.object(self.cache_module.tempfile, "mkstemp", side_effect=no_space):
            result = await self.cache.get_or_generate_audio(text="Hello", **IDENTITY, generate=generate)
            fixed = await self.cache.get_or_generate(text="Fixed", **IDENTITY,
                                                     generate=AsyncMock(return_value=b"pcm"))
            stored = await self.cache.store_audio(text="Stored", **IDENTITY, extension="wav", audio=b"x")
        self.assertEqual((result, fixed, stored), (("mp3", b"paid audio", False), (b"pcm", False), False))
        self.assertEqual(self.cache.skipped_writes, 3)
        self.assertEqual([p for p in self.directory.rglob("*") if p.is_file()], [])
