"""Cloud STT failures of any kind must reach the local fallback, and a faulty
local provider must end in a clean ERROR result rather than an exception."""
import asyncio
from importlib import import_module
from types import SimpleNamespace
from typing import Any
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

import test_assist_bridge as bridge_harness


async def _audio():
    yield b"\x00\x01" * 100


class STTFallbackPathTests(IsolatedAsyncioTestCase):
    # Reuse the HA/aiohttp stubs from the assist bridge suite without
    # re-running that suite's tests in this module.
    setUp = bridge_harness.AssistBridgeTests.setUp
    _hass_with_executor = staticmethod(bridge_harness.AssistBridgeTests._hass_with_executor)
    # Set by the borrowed setUp.
    entry: Any
    session: Any
    request: Any
    response: Any

    def _provider(self):
        return import_module("custom_components.declan_two.stt")

    @staticmethod
    def _engine(provider, *, text="hello"):
        return SimpleNamespace(
            check_metadata=Mock(return_value=True),
            async_process_audio_stream=AsyncMock(
                return_value=provider.stt.SpeechResult(text, "success")),
        )

    async def test_unexpected_cloud_errors_still_reach_local_fallback(self):
        provider = self._provider()
        self.entry.options = {"openai_stt_api_key": "key", "local_stt_entity": "stt.local"}
        entity = provider.DeclanOpenAISTT(object(), self.entry)
        engine = self._engine(provider)
        failures = (
            RuntimeError("Session is closed"),
            TypeError("bad header"),
            AttributeError("transport"),
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad"),
        )
        with patch.object(provider.stt, "async_get_speech_to_text_entity", return_value=engine, create=True):
            for failure in failures:
                with self.subTest(failure=type(failure).__name__):
                    self.session.post.side_effect = failure
                    with self.assertLogs(provider._LOGGER, "WARNING") as logs:
                        result = await entity.async_process_audio_stream(SimpleNamespace(language="en"), _audio())
                    self.assertEqual((result.result, result.text), ("success", "hello"))
                    # Diagnostics name the failure type, never the audio or key.
                    self.assertIn(type(failure).__name__, "\n".join(logs.output))
                    self.assertNotIn("key", "\n".join(logs.output).replace("API key", ""))
        self.assertEqual(engine.async_process_audio_stream.await_count, len(failures))

    async def test_missing_api_key_falls_back_instead_of_failing(self):
        provider = self._provider()
        self.entry.options = {"openai_stt_enabled": True, "local_stt_entity": "stt.local"}
        engine = self._engine(provider)
        with patch.object(provider.stt, "async_get_speech_to_text_entity", return_value=engine, create=True):
            result = await provider.DeclanOpenAISTT(object(), self.entry).async_process_audio_stream(
                SimpleNamespace(language="en"), _audio())
        self.assertEqual(result.result, "success")
        self.session.post.assert_not_called()

    async def test_cancellation_is_never_swallowed_by_the_cloud_path(self):
        provider = self._provider()
        self.entry.options = {"openai_stt_api_key": "key", "local_stt_entity": "stt.local"}
        self.session.post.side_effect = asyncio.CancelledError
        engine = self._engine(provider)
        with patch.object(provider.stt, "async_get_speech_to_text_entity", return_value=engine, create=True), \
                self.assertRaises(asyncio.CancelledError):
            await provider.DeclanOpenAISTT(object(), self.entry).async_process_audio_stream(
                SimpleNamespace(language="en"), _audio())
        engine.async_process_audio_stream.assert_not_awaited()

    async def test_faulty_local_provider_ends_in_clean_error(self):
        provider = self._provider()
        self.entry.options = {"local_stt_entity": "stt.local"}
        entity = provider.DeclanOpenAISTT(object(), self.entry)
        faults = {
            "processing raises": SimpleNamespace(check_metadata=Mock(return_value=True),
                                                 async_process_audio_stream=AsyncMock(side_effect=RuntimeError("boom"))),
            "metadata raises": SimpleNamespace(check_metadata=Mock(side_effect=KeyError("rate")),
                                               async_process_audio_stream=AsyncMock()),
            "metadata rejected": SimpleNamespace(check_metadata=Mock(return_value=False),
                                                 async_process_audio_stream=AsyncMock()),
            "returns None": SimpleNamespace(check_metadata=Mock(return_value=True),
                                            async_process_audio_stream=AsyncMock(return_value=None)),
            "returns error": SimpleNamespace(check_metadata=Mock(return_value=True),
                                             async_process_audio_stream=AsyncMock(
                                                 return_value=provider.stt.SpeechResult(None, "error"))),
            "returns blank text": SimpleNamespace(check_metadata=Mock(return_value=True),
                                                  async_process_audio_stream=AsyncMock(
                                                      return_value=provider.stt.SpeechResult("  ", "success"))),
            "lookup raises": None,
        }
        for name, engine in faults.items():
            with self.subTest(fault=name):
                lookup = (Mock(side_effect=RuntimeError("registry")) if engine is None
                          else Mock(return_value=engine))
                with patch.object(provider.stt, "async_get_speech_to_text_entity", lookup, create=True):
                    result = await entity._fallback(None, b"\0\0", {})
                self.assertEqual(result.result, "error")

    async def test_unavailable_configured_entity_uses_wyoming_bridge_when_configured(self):
        provider = self._provider()
        wyoming = import_module("custom_components.declan_two.wyoming_speaker_stt")
        self.entry.options = {"local_stt_entity": "stt.renamed_or_disabled",
                              "wyoming_bridge_enabled": True, "wyoming_bridge_host": "local.test"}
        engine = self._engine(provider)
        entity = provider.DeclanOpenAISTT(self._hass_with_executor(), self.entry)
        with patch.object(provider.stt, "async_get_speech_to_text_entity", return_value=None, create=True), \
                patch.object(wyoming, "DeclanWyomingVoiceBridge", return_value=engine):
            result = await entity._fallback(None, b"\0\0", {})
        self.assertEqual((result.result, result.text), ("success", "hello"))
        # Without a Wyoming bridge there is nothing else to try.
        self.entry.options = {"local_stt_entity": "stt.renamed_or_disabled"}
        with patch.object(provider.stt, "async_get_speech_to_text_entity", return_value=None, create=True):
            self.assertEqual((await entity._fallback(None, b"\0\0", {})).result, "error")

    async def test_blank_or_missing_local_entity_option_is_tolerated(self):
        provider = self._provider()
        wyoming = import_module("custom_components.declan_two.wyoming_speaker_stt")
        engine = self._engine(provider)
        entity = provider.DeclanOpenAISTT(self._hass_with_executor(), self.entry)
        for value in (None, "", "   "):
            with self.subTest(value=value):
                self.entry.options = {"local_stt_entity": value,
                                      "wyoming_bridge_enabled": True, "wyoming_bridge_host": "local.test"}
                with patch.object(wyoming, "DeclanWyomingVoiceBridge", return_value=engine):
                    self.assertEqual((await entity._fallback(None, b"\0\0", {})).result, "success")
