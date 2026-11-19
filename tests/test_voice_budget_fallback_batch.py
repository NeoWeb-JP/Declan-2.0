"""Durable primary TTS credit reservations and batched fallback accounting."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import AsyncMock


PATH = Path(__file__).resolve().parents[1] / "custom_components" / "declan_two" / "voice_budget.py"
SPEC = importlib.util.spec_from_file_location("declan_voice_budget_test", PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Cannot load VoiceBudget test module")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
VoiceBudget = MODULE.VoiceBudget


class Store:
    def __init__(self):
        self.value: dict[str, int] | None
        self.value = None
        self.saves = []
        self.async_save = AsyncMock(side_effect=self.save)

    async def save(self, value):
        self.value = dict(value)
        self.saves.append(dict(value))

    async def async_load(self):
        return self.value


class VoiceBudgetBatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_primary_reservations_are_immediately_persisted_and_capped(self):
        store = Store()
        budget = VoiceBudget(store=store, today=lambda: "2026-11-18")
        await budget.reserve("abc", "primary", limit=6)
        await budget.reserve("def", "primary", limit=6)
        self.assertEqual(len(store.saves), 2)
        assert store.value is not None
        self.assertEqual(store.value["primary_characters"], 6)
        with self.assertRaisesRegex(ValueError, "limit reached"):
            await budget.reserve("extra", "primary", limit=6)
        self.assertEqual(len(store.saves), 2)
        restarted = VoiceBudget(store=store, today=lambda: "2026-11-18")
        await restarted.load()
        with self.assertRaisesRegex(ValueError, "limit reached"):
            await restarted.reserve("again", "primary", limit=6)

    async def test_fallback_reservations_are_batched_but_counted_in_memory(self):
        store = Store()
        budget = VoiceBudget(store=store, today=lambda: "2026-11-18")
        for count in range(1, MODULE.FALLBACK_SAVE_BATCH):
            await budget.reserve("Hi", "fallback")
            self.assertEqual(budget.snapshot()["fallback_attempts"], count)
            store.async_save.assert_not_awaited()
        await budget.reserve("Hi", "fallback")
        store.async_save.assert_awaited_once()
        assert store.value is not None
        self.assertEqual(store.value["fallback_attempts"], MODULE.FALLBACK_SAVE_BATCH)
        assert store.value is not None
        self.assertEqual(store.value["fallback_characters"], MODULE.FALLBACK_SAVE_BATCH * 2)

    async def test_primary_save_durably_includes_prior_fallback_usage(self):
        store = Store()
        budget = VoiceBudget(store=store, today=lambda: "2026-11-18")
        await budget.reserve("fallback", "fallback")
        await budget.reserve("primary", "primary", limit=20)
        assert store.value is not None
        self.assertEqual(store.value["fallback_attempts"], 1)
        assert store.value is not None
        self.assertEqual(store.value["primary_attempts"], 1)
        self.assertTrue(await budget.flush())
        self.assertEqual(len(store.saves), 1)

    async def test_clean_shutdown_flushes_pending_fallback_usage(self):
        store = Store()
        budget = VoiceBudget(store=store, today=lambda: "2026-11-18")
        await budget.reserve("backup", "fallback")
        self.assertTrue(await budget.flush())
        assert store.value is not None
        self.assertEqual(store.value["fallback_attempts"], 1)
        self.assertTrue(await budget.flush())
        self.assertEqual(len(store.saves), 1)
        restarted = VoiceBudget(store=store, today=lambda: "2026-11-18")
        await restarted.load()
        self.assertEqual(restarted.snapshot()["fallback_attempts"], 1)

    async def test_failed_primary_save_blocks_provider_and_does_not_spend(self):
        store = Store()
        store.async_save.side_effect = OSError("private-token")
        budget = VoiceBudget(store=store)
        with self.assertRaisesRegex(ValueError, "no request sent"):
            await budget.reserve("paid request", "primary", limit=100)
        self.assertFalse(budget.available)
        self.assertEqual(budget.snapshot()["primary_characters"], 0)
        with self.assertRaisesRegex(ValueError, "accounting is unavailable"):
            await budget.reserve("retry", "primary", limit=100)
        self.assertEqual(store.async_save.await_count, 1)

    async def test_failed_fallback_flush_does_not_claim_storage_is_healthy(self):
        store = Store()
        budget = VoiceBudget(store=store)
        await budget.reserve("backup", "fallback")
        store.async_save.side_effect = OSError("secret path")
        self.assertFalse(await budget.flush())
        self.assertFalse(budget.snapshot()["storage_available"])
        with self.assertRaisesRegex(ValueError, "accounting is unavailable"):
            await budget.reserve("paid", "primary", limit=100)

    async def test_concurrent_primary_reservations_cannot_overrun_limit(self):
        import asyncio
        store = Store()
        budget = VoiceBudget(store=store)
        async def attempt():
            try:
                await budget.reserve("abc", "primary", limit=15)
                return True
            except ValueError:
                return False
        results = await asyncio.gather(*(attempt() for _ in range(20)))
        self.assertEqual(sum(results), 5)
        assert store.value is not None
        self.assertEqual(store.value["primary_characters"], 15)
        self.assertEqual(len(store.saves), 5)


if __name__ == "__main__":
    unittest.main()
