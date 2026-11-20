"""Test the bridge against a fake Home Assistant host and HTTP client."""

from importlib import import_module
from collections import namedtuple
from io import BytesIO
from types import ModuleType, SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, Mock, patch
import wave


class AssistBridgeTests(IsolatedAsyncioTestCase):
    async def test_token_verification_returns_typed_status_without_retaining_credentials(self):
        statuses = self.config.TokenVerificationStatus
        self.session.get.return_value = MagicMock()
        probe = self.session.get.return_value.__aenter__.return_value
        for http_status, expected in ((200, statuses.VALID), (401, statuses.INVALID_AUTH),
                (403, statuses.INVALID_AUTH), (503, statuses.CANNOT_CONNECT), (302, statuses.CANNOT_CONNECT)):
            with self.subTest(status=http_status):
                probe.status = http_status
                result = await self.config.verify_declan_token_result(None, "http://declan.invalid", "secret-token")
                self.assertIs(result.status, expected)
                self.assertEqual(result.as_legacy_error(), None if expected is statuses.VALID else expected.value)
                self.assertNotIn("secret-token", str(result))
                self.assertNotIn("declan.invalid", str(result))
                self.assertFalse(self.session.get.call_args.kwargs["allow_redirects"])
                self.assertEqual(self.session.get.call_args.kwargs["headers"], {"Authorization": "Bearer secret-token"})
                with self.assertRaises(AttributeError):
                    result.status = statuses.VALID
        for error in (TimeoutError("secret timeout"), OSError("secret provider error")):
            with patch.object(self.session, "get", side_effect=error):
                result = await self.config.verify_declan_token_result(None, "http://declan.invalid", "secret-token")
            self.assertIs(result.status, statuses.CANNOT_CONNECT)

    async def test_token_verification_legacy_adapter_preserves_none_or_error_keys(self):
        for status in self.config.TokenVerificationStatus:
            result = self.config.TokenVerificationResult(status)
            with patch.object(self.config, "verify_declan_token_result", return_value=result):
                error = await self.config.verify_declan_token(None, "http://declan.invalid", "token")
            self.assertEqual(error, result.as_legacy_error())
            if error is not None:
                self.assertIs(type(error), str)

    async def test_setup_reconfigure_and_reauth_consume_typed_verification_directly(self):
        self.session.get.return_value = MagicMock()
        for step in ("user", "reconfigure", "reauth_confirm"):
            flow = self.config.DeclanTwoConfigFlow()
            flow.hass = SimpleNamespace()
            flow._get_reconfigure_entry = Mock(return_value=self.entry)
            flow._get_reauth_entry = Mock(return_value=self.entry)
            flow.async_show_form = Mock(side_effect=lambda **kwargs: kwargs["errors"])
            flow.async_set_unique_id = AsyncMock()
            flow._abort_if_unique_id_configured = Mock()
            flow.async_create_entry = Mock(return_value={"created": True})
            flow.async_update_reload_and_abort = Mock(return_value={"updated": True})
            payload = {"url": "http://declan.invalid", "token": "n" * 32}
            probe = self.session.get.return_value.__aenter__.return_value
            with self.subTest(step=step), patch.object(self.config, "verify_declan_token", side_effect=AssertionError("legacy verification")):
                probe.status = 401
                self.assertEqual(await getattr(flow, "async_step_" + step)(payload), {"base": "invalid_auth"})
                flow.async_create_entry.assert_not_called()
                flow.async_update_reload_and_abort.assert_not_called()
                probe.status = 200
                result = await getattr(flow, "async_step_" + step)(payload)
                self.assertEqual(result, {"created": True} if step == "user" else {"updated": True})

    def setUp(self):
        class ConfigFlow:
            def __init_subclass__(cls, **kwargs):
                super().__init_subclass__()

        module_names = (
            "aiohttp", "voluptuous", "homeassistant", "homeassistant.helpers",
            "homeassistant.helpers.aiohttp_client", "homeassistant.helpers.entity_registry", "homeassistant.components",
            "homeassistant.components.tts", "homeassistant.components.http", "homeassistant.exceptions", "homeassistant.helpers.storage",
            "wyoming", "wyoming.client", "wyoming.asr", "wyoming.audio", "wyoming.error",
        )
        modules = {name: ModuleType(name) for name in module_names}
        vars(modules["aiohttp"])['ClientError'] = OSError
        vars(modules["aiohttp"])['ClientTimeout'] = Mock()
        vars(modules["aiohttp"])['web'] = SimpleNamespace(json_response=Mock())
        vars(modules["homeassistant.components.http"])['HomeAssistantView'] = object
        self.form = vars(modules["aiohttp"])['FormData'] = Mock()
        vars(modules["voluptuous"])['Schema'] = Mock()
        vars(modules["voluptuous"])['Required'] = lambda name, **kwargs: name
        vars(modules["voluptuous"])['Optional'] = lambda name, **kwargs: name
        for validator in ("In", "All", "Coerce", "Range", "Length"):
            setattr(modules["voluptuous"], validator, Mock())
        vars(modules["homeassistant.components"])['tts'] = modules["homeassistant.components.tts"]
        class FakeTextToSpeechEntity:
            async def async_will_remove_from_hass(self):
                return None
        vars(modules["homeassistant.components.tts"])['TextToSpeechEntity'] = FakeTextToSpeechEntity
        vars(modules["homeassistant.components.tts"])['get_engine_instance'] = Mock(return_value=None)
        vars(modules["homeassistant.exceptions"])['HomeAssistantError'] = type("HomeAssistantError", (Exception,), {})
        vars(modules["homeassistant.helpers.storage"])['Store'] = Mock()
        for suffix, names in {
            "client": ("AsyncTcpClient",), "asr": ("Transcribe", "Transcript"),
            "audio": ("AudioStart", "AudioChunk", "AudioStop"), "error": ("Error",),
        }.items():
            for name in names:
                setattr(modules[f"wyoming.{suffix}"], name, Mock())
        vars(modules["homeassistant"])['config_entries'] = SimpleNamespace(ConfigFlow=ConfigFlow, OptionsFlowWithReload=object)
        vars(modules["homeassistant.helpers"])['selector'] = SimpleNamespace(
            TextSelector=Mock(), TextSelectorConfig=Mock(), TextSelectorType=SimpleNamespace(PASSWORD="password")
        )
        self.intent = vars(modules["homeassistant.helpers"])['intent'] = SimpleNamespace(
            IntentResponse=Mock(),
            IntentResponseErrorCode=SimpleNamespace(FAILED_TO_HANDLE="failed_to_handle"),
        )
        vars(modules["homeassistant.components"])['conversation'] = SimpleNamespace(
            ConversationEntity=object, ConversationResult=SimpleNamespace
        )
        vars(modules["homeassistant.components"])['stt'] = SimpleNamespace(
            SpeechToTextEntity=object, SpeechResult=namedtuple("SpeechResult", "text result"),
            SpeechResultState=SimpleNamespace(SUCCESS="success", ERROR="error"),
        )
        self.session = Mock()
        self.request = self.session.post.return_value = MagicMock()
        self.response = self.request.__aenter__.return_value
        self.response.status = 200
        self.response.json = AsyncMock(return_value={"reply": "Morning", "session_id": "new"})
        vars(modules["homeassistant.helpers.aiohttp_client"])['async_get_clientsession'] = Mock(return_value=self.session)
        vars(modules["homeassistant.helpers.entity_registry"])['async_get'] = Mock(
            return_value=SimpleNamespace(async_get_entity_id=Mock(
                return_value="tts.declan_2_0_voice_manager"
            ))
        )
        vars(modules["homeassistant.helpers"])['entity_registry'] = modules["homeassistant.helpers.entity_registry"]
        self.enterContext(patch.dict("sys.modules", modules))
        self.component = import_module("custom_components.declan_two")
        self.conversation = import_module("custom_components.declan_two.conversation")
        self.config = import_module("custom_components.declan_two.config_flow")
        self.entry = SimpleNamespace(entry_id="entry", data={"url": "http://declan.invalid", "token": "x" * 32},
                                     async_on_unload=Mock())

    async def test_assist_forwards_origin_and_handles_invalid_response(self):
        add = Mock()
        await self.conversation.async_setup_entry(None, self.entry, add)
        agent = add.call_args.args[0][0]
        agent.hass = object()
        self.assertEqual(agent.supported_languages, ["en"])
        user_input = SimpleNamespace(text="good morning", language="en", conversation_id="old",
                                     device_id="device", satellite_id="assist_satellite.bedroom",
                                     context=SimpleNamespace(user_id="user"))
        result = await agent.async_process(user_input)
        self.assertEqual(result.conversation_id, "new")
        self.assertEqual(self.session.post.call_args.kwargs["json"]["satellite_id"], "assist_satellite.bedroom")
        self.assertFalse(self.session.post.call_args.kwargs["allow_redirects"])
        self.intent.IntentResponse.return_value.async_set_speech.assert_called_once_with("Morning")
        self.assertNotIn("speaker", self.session.post.call_args.kwargs["json"])
        class SpeakerTranscript(str):
            jarvis_speaker = ("match-123", "Ed", 0.91)

        user_input.text = SpeakerTranscript("good morning")
        user_input.text.capture_level = {"ended_at": 123, "duration": 2, "rms": 0.4}
        await agent.async_process(user_input)
        self.assertEqual(self.session.post.call_args.kwargs["json"]["capture"], user_input.text.capture_level)
        self.assertEqual(self.session.post.call_args.kwargs["json"]["speaker"], {
            "interaction_id": "match-123", "name": "Ed", "confidence": 0.91,
        })
        self.response.json.return_value = {"reply": 42, "session_id": "wrong"}
        result = await agent.async_process(user_input)
        self.assertEqual(result.conversation_id, "old")
        self.intent.IntentResponse.return_value.async_set_error.assert_called_once()

    async def test_retry_continuation_is_explicit_and_errors_never_keep_listening(self):
        agent = self.conversation.DeclanTwoAgent(self.entry)
        agent.hass = object()
        user_input = SimpleNamespace(text='office light on it',language='en',conversation_id='old',
                                     device_id='device',context=SimpleNamespace(user_id='user'))
        self.response.json.return_value = {'reply':'Could you say it another way?', 'session_id':'retry',
                                           'continue_conversation':True}
        self.assertTrue((await agent.async_process(user_input)).continue_conversation)
        self.response.json.return_value = {'reply':'Sorted', 'session_id':'retry','continue_conversation':False}
        self.assertFalse((await agent.async_process(user_input)).continue_conversation)
        self.response.status = 502
        self.assertFalse((await agent.async_process(user_input)).continue_conversation)

    async def test_event_logging_and_unload(self):
        hass = SimpleNamespace(config_entries=SimpleNamespace(async_forward_entry_setups=AsyncMock(),
                                                              async_unload_platforms=AsyncMock(return_value=True)),
                               bus=SimpleNamespace(async_listen=Mock()), data={},
                               services=SimpleNamespace(async_register=Mock(), async_remove=Mock(),
                                                        async_call=AsyncMock()))
        self.entry.options = {"tts_enabled": True, "primary_tts": "tts.example",
                              "overnight_announcement_outputs": "media_player.kitchen"}
        self.assertTrue(await self.component.async_setup_entry(hass, self.entry))
        domain, service, announce = hass.services.async_register.call_args.args
        # The production callback must have its own clock imports. A mocked
        # clock in this test must not conceal missing runtime imports.
        from datetime import datetime as real_datetime, time as real_time
        self.assertIs(announce.__globals__["datetime"], real_datetime)
        self.assertIs(announce.__globals__["time"], real_time)
        self.assertEqual((domain, service), ("declan_two", "announce"))
        with patch.dict(announce.__globals__, {"datetime": Mock(), "time": __import__("datetime").time}) as globals_:
            clock = globals_["datetime"]
            clock.now.return_value.astimezone.return_value.time.return_value = __import__("datetime").time(23, 30)
            await announce(SimpleNamespace(data={"kind": "ev_reminder", "message": "Charge",
                                                 "entity_id": "media_player.kitchen"}))
            hass.services.async_call.assert_not_awaited()
            await announce(SimpleNamespace(data={"kind": "smoke", "message": "Smoke detected",
                                                 "entity_id": "media_player.other"}))
            hass.services.async_call.assert_not_awaited()
            await announce(SimpleNamespace(data={"kind": "smoke", "message": "Smoke detected",
                                                 "entity_id": "media_player.kitchen"}))
            hass.services.async_call.assert_awaited_once()
            hass.services.async_call.reset_mock()
            await announce(SimpleNamespace(data={"kind": None, "message": "Unknown category",
                                                 "entity_id": "media_player.kitchen"}))
            hass.services.async_call.assert_not_awaited()
            await announce(SimpleNamespace(data={"kind": "security", "message": "x" * 1001,
                                                 "entity_id": "media_player.kitchen"}))
            hass.services.async_call.assert_not_awaited()
            await announce(SimpleNamespace(data={"kind": "carbon_monoxide", "message": "CO alarm",
                                                 "entity_id": "media_player.kitchen"}))
            hass.services.async_call.assert_awaited_once()
            self.assertEqual(
                hass.services.async_call.call_args.args[:2], ("tts", "speak")
            )
            self.assertEqual(
                hass.services.async_call.call_args.args[2]["entity_id"],
                "tts.declan_2_0_voice_manager"
            )
        # The same service accepts ordinary announcements during the day,
        # but cannot fall back to raw TTS if Declan's voice entity is absent.
        with patch.dict(announce.__globals__, {"datetime": Mock(), "time": __import__("datetime").time}) as globals_:
            globals_["datetime"].now.return_value.astimezone.return_value.time.return_value = __import__("datetime").time(12, 0)
            hass.services.async_call.reset_mock()
            await announce(SimpleNamespace(data={"kind": "reminder", "message": "Lunch",
                                                 "entity_id": "media_player.other"}))
            hass.services.async_call.assert_awaited_once()
            hass.services.async_call.reset_mock()
            with patch.object(
                announce.__globals__["entity_registry"], "async_get",
                return_value=SimpleNamespace(async_get_entity_id=Mock(return_value=None)),
            ) if "entity_registry" in announce.__globals__ else patch(
                "homeassistant.helpers.entity_registry.async_get",
                return_value=SimpleNamespace(async_get_entity_id=Mock(return_value=None)),
            ):
                await announce(SimpleNamespace(data={"kind": "reminder", "message": "Lunch",
                                                     "entity_id": "media_player.other"}))
            hass.services.async_call.assert_not_awaited()
        # The preceding daytime override has ended. Explicitly pin the
        # overnight clock for all suppression assertions below.
        with patch.dict(announce.__globals__, {"datetime": Mock(), "time": __import__("datetime").time}) as globals_:
            globals_["datetime"].now.return_value.astimezone.return_value.time.return_value = __import__("datetime").time(23, 30)
            for category in ("unknown", "ev_reminder", "music", "routine", "", None):
                hass.services.async_call.reset_mock()
                await announce(SimpleNamespace(data={"kind": category, "message": "Reminder",
                                                     "entity_id": "media_player.kitchen"}))
                hass.services.async_call.assert_not_awaited()
            for invalid_destination in (
                "media_player.", "media_player.kitchen,media_player.other",
                "media_player.Kitchen", "media_player.kitchen extra",
            ):
                hass.services.async_call.reset_mock()
                await announce(SimpleNamespace(data={"kind": "security", "message": "Alert",
                                                     "entity_id": invalid_destination}))
                hass.services.async_call.assert_not_awaited()
            self.entry.options["overnight_announcement_outputs"] = None
            hass.services.async_call.reset_mock()
            await announce(SimpleNamespace(data={"kind": "security", "message": "Alert",
                                                 "entity_id": "media_player.kitchen"}))
            hass.services.async_call.assert_not_awaited()
            self.entry.options["overnight_announcement_outputs"] = "media_player.kitchen"
        internal = hass.data["declan_two"]["record_assist_reply"]
        await internal({"message": "internal request", "reply": "internal response"})
        self.assertEqual(self.session.post.call_args.kwargs["json"]["message"], "internal request")
        self.session.post.reset_mock()
        await internal("not a dictionary")
        self.session.post.assert_not_called()
        # An arbitrary HA integration can publish bus events. Never register a
        # listener that would forward their payload to privileged history storage.
        hass.bus.async_listen.assert_not_called()
        await internal({"message": "good morning", "reply": "Morning", "outcome": "partial"})
        self.assertTrue(self.session.post.call_args.args[0].endswith("/api/assist/history"))
        self.assertEqual(self.session.post.call_args.kwargs["json"]["outcome"], "partial")
        self.session.post.reset_mock()
        for bad_event in (
            {"message": "hello", "reply": "ok", "session_id": {"unexpected": "object"}},
            {"message": "hello", "reply": "ok", "outcome": "x" * 129},
            {"message": "hello", "reply": "ok", "routine_status": 42},
            {"message": "hello", "reply": "ok", "steps": {"unexpected": "object"}},
            {"message": "hello", "reply": "ok", "steps": ["x"] * 51},
            {"message": "hello", "reply": "ok", "steps": [None]},
        ):
            with self.subTest(event=bad_event):
                await internal(bad_event)
                self.session.post.assert_not_called()
        await internal({"message": "hello", "reply": "ok",
                        "session_id": "session-1", "steps": ["step"]})
        self.assertEqual(self.session.post.call_args.kwargs["json"]["steps"], ["step"])
        self.assertTrue(await self.component.async_unload_entry(hass, self.entry))

    async def test_duplicate_and_stop_finish_without_setting_empty_speech(self):
        agent = self.conversation.DeclanTwoAgent(self.entry)
        agent.hass = object()
        user_input = SimpleNamespace(text='dinner time', language='en', conversation_id='old', device_id='device',
                                     context=SimpleNamespace(user_id='user'))
        for outcome in ('duplicate', 'confirmed'):
            self.response.json.return_value = {'reply': '', 'session_id': 'new', 'outcome': outcome}
            await agent.async_process(user_input)
        self.intent.IntentResponse.return_value.async_set_speech.assert_not_called()
        self.intent.IntentResponse.return_value.async_set_error.assert_not_called()

    async def test_cloud_failure_replays_audio_to_local_stt_once_and_preserves_capture(self):
        provider = import_module('custom_components.declan_two.stt')
        models = import_module('custom_components.declan_two.speaker_models')
        self.entry.options = {'openai_stt_api_key': 'key', 'local_stt_entity': 'stt.local'}
        entity = provider.DeclanOpenAISTT(object(), self.entry)
        received = []
        async def local(metadata, stream):
            received.append(b''.join([chunk async for chunk in stream]))
            return provider.stt.SpeechResult(models.SpeakerTranscript('hello', ('id', 'Edd', .9)), 'success')
        engine = SimpleNamespace(check_metadata=Mock(return_value=True), async_process_audio_stream=AsyncMock(side_effect=local))
        async def audio():
            yield b'\x00\x01' * 100
        with patch.object(provider.stt, 'async_get_speech_to_text_entity', return_value=engine, create=True):
            for failure in ('http', 'timeout', 'empty', 'malformed'):
                self.response.status = 503 if failure == 'http' else 200
                self.request.__aenter__.side_effect = TimeoutError if failure == 'timeout' else None
                self.response.json.side_effect = ValueError if failure == 'malformed' else None
                self.response.json.return_value = {'text': ''}
                result = await entity.async_process_audio_stream(SimpleNamespace(language='en'), audio())
                self.assertEqual(result.result, 'success')
                self.assertEqual(result.text.jarvis_speaker, ('id', 'Edd', .9))
                self.assertAlmostEqual(result.text.capture_level['duration'], 100 / 16000)
        self.assertEqual(engine.async_process_audio_stream.await_count, 4)
        self.assertEqual(received, [b'\x00\x01' * 100] * 4)

    async def test_local_stt_failure_missing_provider_and_recursive_provider_fail_cleanly(self):
        provider = import_module('custom_components.declan_two.stt')
        self.entry.options = {'local_stt_entity': 'stt.local'}
        entity = provider.DeclanOpenAISTT(object(), self.entry)
        local = SimpleNamespace(check_metadata=Mock(return_value=True), async_process_audio_stream=AsyncMock(side_effect=TimeoutError))
        for engine in (None, entity, local):
            with patch.object(provider.stt, 'async_get_speech_to_text_entity', return_value=engine, create=True):
                result = await entity._fallback(None, b'\0\0', {'ended_at': 1, 'duration': 1, 'rms': 0})
                self.assertEqual(result.result, 'error')
        local.async_process_audio_stream.assert_awaited_once()

    @staticmethod
    def _hass_with_executor():
        async def run(func, *args):
            return func(*args)
        return SimpleNamespace(async_add_executor_job=run)

    async def test_wyoming_configuration_is_used_as_local_fallback(self):
        provider = import_module('custom_components.declan_two.stt')
        bridge = import_module('custom_components.declan_two.wyoming_speaker_stt')
        self.entry.options = {'wyoming_bridge_enabled': True, 'wyoming_bridge_host': 'local.test'}
        engine = SimpleNamespace(check_metadata=Mock(return_value=True), async_process_audio_stream=AsyncMock(
            return_value=provider.stt.SpeechResult('hello', 'success')))
        with patch.object(bridge, 'DeclanWyomingVoiceBridge', return_value=engine):
            result = await provider.DeclanOpenAISTT(self._hass_with_executor(), self.entry)._fallback(None, b'\0\0', {})
        self.assertEqual(result.result, 'success')

    async def test_local_fallback_deadline_and_external_cancellation(self):
        import asyncio
        provider = import_module('custom_components.declan_two.stt')
        self.entry.options = {'local_stt_entity': 'stt.local'}
        entity = provider.DeclanOpenAISTT(object(), self.entry)
        async def stall(metadata, stream):
            await asyncio.Event().wait()
        engine = SimpleNamespace(check_metadata=Mock(return_value=True), async_process_audio_stream=AsyncMock(side_effect=stall))
        timeout = asyncio.timeout
        with patch.object(provider.stt, 'async_get_speech_to_text_entity', return_value=engine, create=True), patch.object(
                provider.asyncio, 'timeout', side_effect=lambda _: timeout(.01)):
            self.assertEqual((await entity._fallback(None, b'\0\0', {})).result, 'error')
        engine.async_process_audio_stream.side_effect = asyncio.CancelledError
        with patch.object(provider.stt, 'async_get_speech_to_text_entity', return_value=engine, create=True):
            with self.assertRaises(asyncio.CancelledError):
                await entity._fallback(None, b'\0\0', {})

    async def test_configuration_rejects_bad_address_and_weak_token(self):
        flow = self.config.DeclanTwoConfigFlow()
        flow.hass = SimpleNamespace()
        self.session.get.return_value = MagicMock()
        self.session.get.return_value.__aenter__.return_value.status = 200
        flow.async_show_form = Mock(side_effect=lambda **kwargs: kwargs["errors"])
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = Mock()
        flow.async_create_entry = Mock(side_effect=lambda **kwargs: kwargs["data"])
        self.assertEqual(await flow.async_step_user(), {})
        self.assertEqual(await flow.async_step_user({"url": "ftp://bad.invalid", "token": "x" * 32}),
                         {"url": "invalid_url"})
        self.assertEqual(await flow.async_step_user({"url": "http://declan.invalid", "token": "short"}),
                         {"token": "invalid_token"})
        self.assertEqual((await flow.async_step_user({"url": "http://declan.invalid/", "token": "x" * 32}))["url"],
                         "http://declan.invalid")
        self.session.get.return_value.__aenter__.return_value.status = 401
        self.assertEqual(await flow.async_step_user({"url": "http://declan.invalid", "token": "x" * 32}),
                         {"base": "invalid_auth"})
        self.session.get.return_value.__aenter__.return_value.status = 503
        self.assertEqual(await flow.async_step_user({"url": "http://declan.invalid", "token": "x" * 32}),
                         {"base": "cannot_connect"})

    async def test_reauth_validates_token_before_updating_entry(self):
        flow = self.config.DeclanTwoConfigFlow()
        flow.hass = SimpleNamespace()
        flow._get_reauth_entry = Mock(return_value=self.entry)
        flow.async_show_form = Mock(side_effect=lambda **kwargs: kwargs["errors"])
        flow.async_update_reload_and_abort = Mock(return_value={"type": "abort"})
        self.session.get.return_value = MagicMock()
        probe = self.session.get.return_value.__aenter__.return_value
        probe.status = 401
        self.assertEqual(await flow.async_step_reauth_confirm({"token": "n" * 32}),
                         {"base": "invalid_auth"})
        flow.async_update_reload_and_abort.assert_not_called()
        probe.status = 503
        self.assertEqual(await flow.async_step_reauth_confirm({"token": "n" * 32}),
                         {"base": "cannot_connect"})
        probe.status = 200
        self.assertEqual(await flow.async_step_reauth_confirm({"token": "n" * 32}),
                         {"type": "abort"})
        flow.async_update_reload_and_abort.assert_called_once_with(
            self.entry, data_updates={"token": "n" * 32},
        )

    async def test_reconfigure_preserves_token_and_rejects_invalid_url(self):
        flow = self.config.DeclanTwoConfigFlow()
        flow.hass = SimpleNamespace()
        flow._get_reconfigure_entry = Mock(return_value=self.entry)
        flow.async_show_form = Mock(side_effect=lambda **kwargs: kwargs["errors"])
        flow.async_update_reload_and_abort = Mock(return_value={"type": "abort"})
        self.session.get.return_value = MagicMock()
        self.session.get.return_value.__aenter__.return_value.status = 200
        self.assertEqual(await flow.async_step_reconfigure({"url": "ftp://invalid", "token": ""}),
                         {"url": "invalid_url"})
        self.assertEqual(await flow.async_step_reconfigure({"url": "http://declan.invalid/", "token": ""}),
                         {"type": "abort"})
        flow.async_update_reload_and_abort.assert_called_once_with(
            self.entry, data_updates={"url": "http://declan.invalid", "token": "x" * 32},
        )

    async def test_openai_options_require_and_preserve_the_key(self):
        flow = self.config.DeclanTwoConfigFlow.async_get_options_flow(self.entry)
        flow.config_entry = SimpleNamespace(options={})
        flow.async_show_form = Mock(side_effect=lambda **kwargs: kwargs["errors"])
        flow.async_create_entry = Mock(side_effect=lambda **kwargs: kwargs["data"])
        settings = {"openai_stt_enabled": True, "openai_stt_model": "gpt-transcribe"}
        self.assertEqual(await flow.async_step_init(settings), {"openai_stt_api_key": "openai_key_required"})
        saved = await flow.async_step_init({**settings, "openai_stt_api_key": "test-key"})
        flow.config_entry.options = saved
        self.assertEqual(await flow.async_step_init(settings), saved)

    async def test_openai_entity_sends_pcm_as_wav_and_returns_transcript(self):
        provider = import_module("custom_components.declan_two.stt")
        self.entry.options = {"openai_stt_api_key": "test-key", "openai_stt_enabled": True}
        add = Mock()
        await provider.async_setup_entry(None, self.entry, add)
        entity = add.call_args.args[0][0]
        self.response.json.return_value = {"text": " What's the time? "}

        async def audio():
            yield b"\x00\x01\x02\x03"

        self.assertEqual(await entity.async_process_audio_stream(None, audio()), ("What's the time?", "success"))
        fields = self.form.return_value.add_field.call_args_list
        with wave.open(BytesIO(fields[0].args[1]), "rb") as recording:
            self.assertEqual((recording.getframerate(), recording.getnchannels(), recording.getsampwidth()), (16000, 1, 2))
            self.assertEqual(recording.readframes(2), b"\x00\x01\x02\x03")
        self.assertIn(("model", "gpt-4o-mini-transcribe"), [field.args for field in fields])
        self.assertIn(("prompt", provider.PROMPT), [field.args for field in fields])
        self.assertFalse(self.session.post.call_args.kwargs["allow_redirects"])

    async def test_stt_custom_vocabulary_is_sent_only_when_enabled(self):
        provider = import_module("custom_components.declan_two.stt")
        self.entry.options = {
            "openai_stt_api_key": "test-key",
            "openai_stt_enabled": True,
            "openai_stt_vocabulary": "Study, Braai",
        }
        entities = Mock()
        await provider.async_setup_entry(None, self.entry, entities)
        entity = entities.call_args.args[0][0]
        self.response.json.return_value = {"text": "Switch on study light"}

        async def audio():
            yield b"\x00\x01\x02\x03"

        await entity.async_process_audio_stream(None, audio())
        self.assertIn(("prompt", provider.PROMPT + " Vocabulary: Study, Braai."),
                      [call.args for call in self.form.return_value.add_field.call_args_list])

    async def test_options_reject_unsafe_vocabulary_and_preserve_existing(self):
        flow = self.config.DeclanTwoConfigFlow.async_get_options_flow(self.entry)
        flow.config_entry = SimpleNamespace(options={"openai_stt_vocabulary": "Kitchen"})
        flow.async_show_form = Mock(side_effect=lambda **kwargs: kwargs["errors"])
        flow.async_create_entry = Mock(side_effect=lambda **kwargs: kwargs["data"])
        settings = {"openai_stt_enabled": False, "openai_stt_model": "gpt-transcribe"}
        self.assertEqual(
            await flow.async_step_init({**settings, "openai_stt_vocabulary": "Kitchen\\nBad"}),
            {"openai_stt_vocabulary": "invalid_stt_vocabulary"},
        )
        saved = await flow.async_step_init(settings)
        self.assertEqual(saved["openai_stt_vocabulary"], "Kitchen")
        cleared = await flow.async_step_init({**settings, "openai_stt_vocabulary": ""})
        self.assertEqual(cleared["openai_stt_vocabulary"], "")

    async def test_guest_mode_helper_options_validate_and_persist(self):
        flow = self.config.DeclanTwoConfigFlow.async_get_options_flow(self.entry)
        flow.config_entry = SimpleNamespace(options={"guest_mode_entity": "input_boolean.old_guest"})
        flow.async_show_form = Mock(side_effect=lambda **kwargs: kwargs["errors"])
        flow.async_create_entry = Mock(side_effect=lambda **kwargs: kwargs["data"])
        fields = {"openai_stt_enabled": False,
                  "openai_stt_model": "gpt-4o-mini-transcribe"}
        for bad in ("sensor.motion", "input_boolean.BadCase", "input_boolean.", "input_boolean.a/../b"):
            with self.subTest(bad=bad):
                self.assertEqual(await flow.async_step_init(
                    {**fields, "guest_mode_entity": bad}),
                    {"guest_mode_entity": "invalid_guest_mode_entity"})
        saved = await flow.async_step_init(
            {**fields, "guest_mode_entity": "input_boolean.house_sitters"})
        self.assertEqual(saved["guest_mode_entity"], "input_boolean.house_sitters")
        flow.config_entry.options = saved
        unchanged = await flow.async_step_init(fields)
        self.assertEqual(unchanged["guest_mode_entity"], "input_boolean.house_sitters")

    async def test_wyoming_is_registered_and_retains_speaker_event(self):
        provider = import_module("custom_components.declan_two.stt")
        bridge = import_module("custom_components.declan_two.wyoming_speaker_stt")
        self.entry.options = {
            "wyoming_bridge_enabled": True, "wyoming_bridge_host": "192.168.0.43",
            "wyoming_bridge_port": 10300,
        }
        add = Mock()
        await provider.async_setup_entry(self._hass_with_executor(), self.entry, add)
        entity = add.call_args.args[0][0]
        bridge.Transcript.is_type.side_effect = lambda name: name == "transcript"
        bridge.Transcript.from_event.return_value.text = "What's the time?"
        client = bridge.AsyncTcpClient.return_value.__aenter__ = AsyncMock()
        client.return_value.write_event = AsyncMock()
        client.return_value.read_event = AsyncMock(side_effect=[
            SimpleNamespace(type="jarvis-speaker", data={
                "speaker": "Jaco", "confidence": 0.32, "interaction_id": "match-1",
            }),
            SimpleNamespace(type="transcript"),
        ])
        bridge.AsyncTcpClient.return_value.__aexit__ = AsyncMock()

        async def audio():
            yield b"\x00\x01"

        transcript, status = await entity.async_process_audio_stream(SimpleNamespace(language="en"), audio())
        self.assertEqual((transcript, status), ("What's the time?", "success"))
        self.assertEqual(transcript.jarvis_speaker, ("match-1", "Jaco", 0.32))
        self.assertEqual(transcript.capture_level["duration"], 1 / 16000)
        self.assertGreater(transcript.capture_level["rms"], 0)
        bridge.AsyncTcpClient.assert_called_once_with("192.168.0.43", 10300)

    async def test_tts_entity_flushes_fallback_usage_on_unload(self):
        platform = import_module("custom_components.declan_two.tts")
        budget = Mock(flush=AsyncMock(return_value=True))
        entity = platform.DeclanVoiceManager(self.entry, Mock(), budget)
        await entity.async_will_remove_from_hass()
        budget.flush.assert_awaited_once()

        budget.flush.reset_mock()
        budget.flush.return_value = False
        with patch.object(platform, "_LOGGER") as logger:
            await entity.async_will_remove_from_hass()
        logger.warning.assert_called_once_with(
            "Declan voice usage could not be saved on unload")

    async def test_voice_manager_reuses_provider_and_legacy_cache_identity(self):
        platform = import_module("custom_components.declan_two.tts")
        self.entry.options = {"tts_enabled": True, "elevenlabs_voice": "declan-voice-id"}
        hass = SimpleNamespace(config=SimpleNamespace(path=Mock(return_value="jarvis_voice_cache")))
        add = Mock()
        with patch.object(platform, "VoiceCache") as cache, patch.object(platform, "VoiceBudget") as budget:
            budget.return_value.load = AsyncMock()
            budget.return_value.reserve = AsyncMock()
            await platform.async_setup_entry(hass, self.entry, add)

            async def cached_audio(**kwargs):
                extension, audio = await kwargs["generate"]()
                return extension, audio, False

            cache.return_value.get_or_generate_audio = AsyncMock(side_effect=cached_audio)
            entity = add.call_args.args[0][0]
            entity.hass = hass
            entity.entity_id = "tts.declan_2_0_voice_manager"
            with patch.object(platform, "quiet_hours", return_value=False), patch.object(platform, "generate_from_existing_tts", AsyncMock(return_value=("mp3", b"audio"))) as generate:
                self.assertEqual(await entity.async_get_tts_audio("Hello", "en", {}), ("mp3", b"audio"))
            generate.assert_awaited_once_with(
                hass, provider_entity_id="tts.elevenlabs_text_to_speech", text="Hello",
                language="en", options={"voice": "declan-voice-id"},
            )
            cache.assert_called_once_with(__import__("pathlib").Path("jarvis_voice_cache"))
            self.assertEqual(cache.return_value.get_or_generate_audio.call_args.kwargs["voice_id"], "v1:declan-voice-id")
