"""Exercise speech persistence, paid-request limits and reusable audio offline."""

import asyncio
from importlib import import_module
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock


# These modules are independent of HA. Load them under a package that does not
# execute the integration's HA-dependent __init__ during standalone testing.
PACKAGE = "declan_speech_tests"
package = ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components/declan_two")]
sys.modules[PACKAGE] = package
cache_module = import_module(PACKAGE + ".voice_cache")
budget_module = import_module(PACKAGE + ".voice_budget")
phrases = import_module(PACKAGE + ".phrase_library")
catalogue_module = import_module(PACKAGE + ".voice_catalog_fallback")

IDENTITY = {"provider": "tts.elevenlabs", "voice_id": "declan-v1", "model": "multilingual-v2"}


class VoiceCacheTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory())) / "cache"
        self.cache = cache_module.VoiceCache(self.directory, min_free_bytes=0)

    async def test_concurrent_requests_share_one_generation_and_survive_restart(self):
        generate = AsyncMock(return_value=("mp3", b"spoken reply"))
        requests = [self.cache.get_or_generate_audio(text="Hello", **IDENTITY, generate=generate) for _ in range(4)]
        results = await asyncio.gather(*requests)
        generate.assert_awaited_once()
        self.assertEqual(sum(not result[2] for result in results), 1)
        reopened = cache_module.VoiceCache(self.directory, min_free_bytes=0)
        self.assertEqual(await reopened.find_cached_audio(text="Hello", **IDENTITY), ("mp3", b"spoken reply"))
        snapshot = await reopened.snapshot(query="HELLO", page=1, page_size=1)
        self.assertEqual((snapshot["count"], snapshot["matched_count"], snapshot["first"], snapshot["last"]), (1, 1, 1, 1))
        self.assertEqual(snapshot["entries"][0]["text"], "Hello")
        self.assertEqual(await reopened.saved_audio(snapshot["entries"][0]["key"], "mp3"), b"spoken reply")
        self.assertEqual((await reopened.snapshot(query="absent"))["matched_count"], 0)

    async def test_different_voice_and_provider_cannot_reuse_another_recording(self):
        generate = AsyncMock(return_value=("wav", b"audio"))
        await self.cache.get_or_generate_audio(text="Hello", **IDENTITY, generate=generate)
        for changed in ({"voice_id": "declan-v2"}, {"provider": "tts.other"}, {"model": "new-model"}):
            self.assertIsNone(await self.cache.find_cached_audio(text="Hello", **{**IDENTITY, **changed}))
        self.assertEqual(self.cache.key(text="Hello", **IDENTITY, settings={"speed": 1, "voice": "a"}),
                         self.cache.key(text="Hello", **IDENTITY, settings={"voice": "a", "speed": 1}))

    async def test_failed_or_invalid_provider_audio_is_not_cached(self):
        for result in (("mp3", b""), ("exe", b"audio"), ("wav", "not bytes")):
            with self.subTest(result=result), self.assertRaises(ValueError):
                await self.cache.get_or_generate_audio(text="Hello", **IDENTITY, generate=AsyncMock(return_value=result))
        with self.assertRaises(TimeoutError):
            await self.cache.get_or_generate_audio(text="Hello", **IDENTITY, generate=AsyncMock(side_effect=TimeoutError))
        self.assertIsNone(await self.cache.find_cached_audio(text="Hello", **IDENTITY))
        self.assertEqual(list(self.directory.rglob("*.mp3")), [])

    async def test_storage_limits_skip_persistence_but_return_generated_audio(self):
        generate = AsyncMock(return_value=("mp3", b"audio"))
        for limits in ({"max_bytes": 1, "min_free_bytes": 0}, {"min_free_bytes": 10**20}):
            cache = cache_module.VoiceCache(self.directory, **limits)
            self.assertEqual(await cache.get_or_generate_audio(text="Hello", **IDENTITY, generate=generate),
                             ("mp3", b"audio", False))
            self.assertEqual(cache.skipped_writes, 1)
            if limits.get("min_free_bytes", 0) == 10**20:
                self.assertFalse((await cache.snapshot())["storage_available"])
            self.assertIsNone(await cache.find_cached_audio(text="Hello", **IDENTITY))

    async def test_replacing_format_removes_old_audio_and_keeps_sentence_metadata(self):
        await self.cache.store_audio(text="Hello", **IDENTITY, extension="mp3", audio=b"old")
        self.assertTrue(await self.cache.store_audio(text="Hello", **IDENTITY, extension="wav", audio=b"new",
                                                    parts=["Hello"], gap_ms=20))
        self.assertEqual(await self.cache.find_cached_audio(text="Hello", **IDENTITY), ("wav", b"new"))
        self.assertEqual(list(self.directory.rglob("*.mp3*")), [])
        entry = (await self.cache.snapshot())["entries"][0]
        self.assertEqual((entry["parts"], entry["gap_ms"]), (["Hello"], 20))
        for extension, audio in (("exe", b"audio"), ("wav", b"")):
            with self.assertRaises(ValueError):
                await self.cache.store_audio(text="Hello", **IDENTITY, extension=extension, audio=audio)

    async def test_old_audio_without_metadata_remains_readable_and_preview_paths_are_bounded(self):
        key = self.cache.key(text="Old reply", **IDENTITY)
        path = self.cache.path_for(key)
        path.parent.mkdir(parents=True)
        path.write_bytes(b"old audio")
        snapshot = await self.cache.snapshot(page=10, page_size=1)
        self.assertEqual(snapshot["page"], 1)
        self.assertEqual(snapshot["entries"][0]["kind"], "legacy")
        self.assertEqual(await self.cache.saved_audio(key, "wav"), b"old audio")
        for bad in ("../private", "g" * 64):
            with self.assertRaises(ValueError):
                self.cache.path_for(bad)
        with self.assertRaises(ValueError):
            self.cache.path_for(key, "txt")
        for invalid in ({"query": "a" * 201}, {"page": 0}, {"page_size": 0}, {"page_size": 101}):
            with self.assertRaises(ValueError):
                await self.cache.snapshot(**invalid)

    async def test_fixed_format_generation_is_coalesced_and_rejects_empty_audio(self):
        generate = AsyncMock(return_value=b"pcm")
        for hit in (False, True):
            self.assertEqual(await self.cache.get_or_generate(text="Hello", **IDENTITY, generate=generate), (b"pcm", hit))
        generate.assert_awaited_once()
        with self.assertRaises(ValueError):
            await self.cache.get_or_generate(text="Empty", **IDENTITY, generate=AsyncMock(return_value=b""))
        with self.assertRaises(ValueError):
            self.cache.key(text="Hello", **IDENTITY, extension="exe")


class VoiceBudgetTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.day = "2026-11-11"
        self.store = SimpleNamespace(async_load=AsyncMock(return_value=None), async_save=AsyncMock())
        self.budget = budget_module.VoiceBudget(self.store, today=lambda: self.day)

    async def test_simultaneous_reservations_cannot_exceed_daily_limit(self):
        await self.budget.load()
        results = await asyncio.gather(*(self.budget.reserve("Hello", "primary", 7) for _ in range(3)), return_exceptions=True)
        self.assertEqual(sum(isinstance(result, ValueError) for result in results), 2)
        snapshot = self.budget.snapshot(limit=7, credit_rate=0.5)
        self.assertEqual((snapshot["primary_characters"], snapshot["primary_attempts"], snapshot["remaining_characters"]), (5, 1, 2))
        self.assertEqual(snapshot["estimated_credits"], 2.5)
        persisted = self.store.async_save.call_args.args[0]
        self.store.async_load.return_value = persisted
        reopened = budget_module.VoiceBudget(self.store, today=lambda: self.day)
        await reopened.load()
        with self.assertRaises(ValueError):
            await reopened.reserve("again", "primary", 7)

    async def test_clock_rollback_preserves_usage_and_next_day_resets_it(self):
        await self.budget.reserve("Hello", "primary", 10)
        self.day = "2026-11-10"
        self.assertEqual(self.budget.snapshot()["primary_characters"], 5)
        self.day = "2026-11-12"
        self.assertEqual(self.budget.snapshot()["primary_characters"], 0)
        await self.budget.reserve("Hello", "fallback")
        self.assertEqual(self.budget.snapshot()["fallback_characters"], 5)
        self.assertEqual(self.budget.snapshot()["primary_characters"], 0)

    async def test_corrupt_or_unwritable_storage_blocks_new_primary_usage(self):
        for bad in ({"bad": "shape"}, {**self.budget.empty(), "day": "invalid"},
                    {**self.budget.empty(), "primary_characters": -1}):
            budget = budget_module.VoiceBudget(self.store, today=lambda: self.day)
            self.store.async_load.return_value = bad
            await budget.load()
            with self.assertRaises(ValueError):
                await budget.reserve("Hello", "primary")
            self.assertFalse(budget.snapshot()["storage_available"])
        self.store.async_save.side_effect = OSError
        with self.assertRaises(ValueError):
            await self.budget.reserve("Hello", "primary")
        self.assertEqual(self.budget.data["primary_attempts"], 0)
        await self.budget.reserve("Hello", "fallback")
        self.assertEqual(self.budget.data["fallback_attempts"], 1)
        for invalid in (True, -1, 10_000_001):
            with self.assertRaises(ValueError):
                self.budget.snapshot(limit=invalid)
        with self.assertRaises(ValueError):
            await self.budget.reserve("Hello", "unknown")
        self.assertIsNone(self.budget.snapshot(credit_rate=float("nan"))["estimated_credits"])


class PhraseLibraryTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory())) / "cache"
        self.cache = cache_module.VoiceCache(self.directory, min_free_bytes=0)
        self.library = phrases.PhraseLibrary(self.cache)
        self.audio = phrases.pcm_wave(b"\x00\x10" * 2400)

    async def test_composed_music_reply_reuses_clips_without_another_paid_request(self):
        message = "Playing Country music from Spotify in the Kitchen."
        parts = phrases.phrase_parts(message)
        self.assertEqual(parts, ["Playing", "Country", "music from Spotify in the", "Kitchen."])
        generate = AsyncMock(return_value=("wav", self.audio))
        first = await self.library.compose(message, IDENTITY, generate)
        second = await self.library.compose(message, IDENTITY, generate)
        self.assertEqual((first[2:], second[2:]), ((False, 4), (True, 0)))
        self.assertEqual(generate.await_count, 4)
        self.assertEqual(phrases.read_pcm(first[1]), phrases.read_pcm(second[1]))
        self.assertIsNone(await self.library.compose("Custom factual warning.", IDENTITY, generate))

    async def test_preview_is_read_only_and_saved_sentence_preserves_exact_wording(self):
        self.assertEqual(await self.library.preview(["Hello"], IDENTITY), {"missing": ["hello"]})
        generate = AsyncMock(return_value=("wav", self.audio))
        saved = await self.library.save_sentence(["Hello", "my bru."], IDENTITY, generate, gap_ms=10)
        self.assertTrue(saved["saved"])
        self.assertEqual((saved["text"], saved["generated_clips"]), ("Hello my bru.", 2))
        preview = await self.library.preview(["Hello", "my bru."], IDENTITY, gap_ms=10)
        self.assertEqual(preview["missing"], [])
        self.assertEqual(preview["extension"], "wav")
        self.assertEqual(generate.await_count, 2)
        self.assertEqual(await self.cache.find_cached_audio(text="Hello my bru.", **IDENTITY), ("wav", preview["audio"]))

    async def test_silent_and_malformed_audio_is_rejected_before_persistence(self):
        for pcm in (b"", b"x"):
            with self.assertRaises(ValueError):
                phrases.pcm_wave(pcm)
        with self.assertRaises(ValueError):
            phrases.join_clips([phrases.pcm_wave(b"\x00\x00" * 20)])
        for clips, gap in (([], 20), ([self.audio], -1), ([self.audio], True)):
            with self.assertRaises(ValueError):
                phrases.join_clips(clips, gap)
        for parts in ([], [""], ["x"] * 9):
            with self.assertRaises(ValueError):
                await self.library.preview(parts, IDENTITY)
        with self.assertRaises(ValueError):
            await phrases.normalise_audio("exe", b"invalid")
        self.assertEqual((await self.cache.snapshot())["count"], 0)


class VoiceCatalogueTests(TestCase):
    def test_cached_fallback_stays_in_the_same_privacy_pool_and_preserves_factual_speech(self):
        catalogue = {"Home": {"general": ["Home one", "Home two", "Home two", "", None]},
                     "Guest": {"general": ["Guest one", "Guest two"], "on": "invalid"}}
        self.assertEqual(catalogue_module.category_alternatives("Home one", catalogue, guest=False), ("Home two",))
        self.assertEqual(catalogue_module.category_alternatives("Home one", catalogue, guest=True), ())
        self.assertEqual(catalogue_module.category_alternatives("Guest one", catalogue, guest=True), ("Guest two",))
        self.assertEqual(catalogue_module.category_alternatives("Temperature is 19 degrees.", catalogue, guest=False), ())
        with TemporaryDirectory() as directory:
            path = Path(directory) / "catalogue.json"
            path.write_text(json.dumps(catalogue), encoding="utf-8")
            self.assertEqual(catalogue_module.load_catalogue(path), catalogue)
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                catalogue_module.load_catalogue(path)
