"""Test the bridge against a fake Home Assistant host and HTTP client."""

from importlib import import_module
from io import BytesIO
from types import ModuleType, SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, Mock, patch
import wave


class AssistBridgeTests(IsolatedAsyncioTestCase):
    def setUp(self):
        class ConfigFlow:
            def __init_subclass__(cls, **kwargs):
                super().__init_subclass__()

        module_names = (
            "aiohttp", "voluptuous", "homeassistant", "homeassistant.helpers",
            "homeassistant.helpers.aiohttp_client", "homeassistant.components",
            "homeassistant.components.tts", "homeassistant.exceptions", "homeassistant.helpers.storage",
            "wyoming", "wyoming.client", "wyoming.asr", "wyoming.audio", "wyoming.error",
        )
        modules = {name: ModuleType(name) for name in module_names}
        modules["aiohttp"].ClientError = OSError
        modules["aiohttp"].ClientTimeout = Mock()
        self.form = modules["aiohttp"].FormData = Mock()
        modules["voluptuous"].Schema = Mock()
        modules["voluptuous"].Required = lambda name, **kwargs: name
        modules["voluptuous"].Optional = lambda name: name
        for validator in ("In", "All", "Coerce", "Range", "Length"):
            setattr(modules["voluptuous"], validator, Mock())
        modules["homeassistant.components"].tts = modules["homeassistant.components.tts"]
        modules["homeassistant.components.tts"].TextToSpeechEntity = object
        modules["homeassistant.components.tts"].get_engine_instance = Mock(return_value=None)
        modules["homeassistant.exceptions"].HomeAssistantError = type("HomeAssistantError", (Exception,), {})
        modules["homeassistant.helpers.storage"].Store = Mock()
        for suffix, names in {
            "client": ("AsyncTcpClient",), "asr": ("Transcribe", "Transcript"),
            "audio": ("AudioStart", "AudioChunk", "AudioStop"), "error": ("Error",),
        }.items():
            for name in names:
                setattr(modules[f"wyoming.{suffix}"], name, Mock())
        modules["homeassistant"].config_entries = SimpleNamespace(ConfigFlow=ConfigFlow, OptionsFlowWithReload=object)
        modules["homeassistant.helpers"].selector = SimpleNamespace(
            TextSelector=Mock(), TextSelectorConfig=Mock(), TextSelectorType=SimpleNamespace(PASSWORD="password")
        )
        self.intent = modules["homeassistant.helpers"].intent = SimpleNamespace(
            IntentResponse=Mock(),
            IntentResponseErrorCode=SimpleNamespace(FAILED_TO_HANDLE="failed_to_handle"),
        )
        modules["homeassistant.components"].conversation = SimpleNamespace(
            ConversationEntity=object, ConversationResult=SimpleNamespace
        )
        modules["homeassistant.components"].stt = SimpleNamespace(
            SpeechToTextEntity=object, SpeechResult=lambda text, result: (text, result),
            SpeechResultState=SimpleNamespace(SUCCESS="success", ERROR="error"),
        )
        self.session = Mock()
        self.request = self.session.post.return_value = MagicMock()
        self.response = self.request.__aenter__.return_value
        self.response.status = 200
        self.response.json = AsyncMock(return_value={"reply": "Morning", "session_id": "new"})
        modules["homeassistant.helpers.aiohttp_client"].async_get_clientsession = Mock(return_value=self.session)
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
        await agent.async_process(user_input)
        self.assertEqual(self.session.post.call_args.kwargs["json"]["speaker"], {
            "interaction_id": "match-123", "name": "Ed", "confidence": 0.91,
        })
        self.response.json.return_value = {"reply": 42, "session_id": "wrong"}
        result = await agent.async_process(user_input)
        self.assertEqual(result.conversation_id, "old")
        self.intent.IntentResponse.return_value.async_set_error.assert_called_once()

    async def test_event_logging_and_unload(self):
        hass = SimpleNamespace(config_entries=SimpleNamespace(async_forward_entry_setups=AsyncMock(),
                                                              async_unload_platforms=AsyncMock(return_value=True)),
                               bus=SimpleNamespace(async_listen=Mock()))
        self.assertTrue(await self.component.async_setup_entry(hass, self.entry))
        name, handler = hass.bus.async_listen.call_args.args
        self.assertEqual(name, "declan_two_assist_reply")
        await handler(SimpleNamespace(data={"message": ""}))
        self.session.post.assert_not_called()
        await handler(SimpleNamespace(data={"message": "good morning", "reply": "Morning", "outcome": "partial"}))
        self.assertTrue(self.session.post.call_args.args[0].endswith("/api/assist/history"))
        self.assertEqual(self.session.post.call_args.kwargs["json"]["outcome"], "partial")
        self.assertTrue(await self.component.async_unload_entry(hass, self.entry))

    async def test_configuration_rejects_bad_address_and_weak_token(self):
        flow = self.config.DeclanTwoConfigFlow()
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
        self.assertIn(("model", "gpt-transcribe"), [field.args for field in fields])
        self.assertFalse(self.session.post.call_args.kwargs["allow_redirects"])

    async def test_wyoming_is_registered_and_retains_speaker_event(self):
        provider = import_module("custom_components.declan_two.stt")
        bridge = import_module("custom_components.declan_two.wyoming_speaker_stt")
        self.entry.options = {
            "wyoming_bridge_enabled": True, "wyoming_bridge_host": "192.168.0.43",
            "wyoming_bridge_port": 10300,
        }
        add = Mock()
        await provider.async_setup_entry(None, self.entry, add)
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
        bridge.AsyncTcpClient.assert_called_once_with("192.168.0.43", 10300)

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
            with patch.object(platform, "generate_from_existing_tts", AsyncMock(return_value=("mp3", b"audio"))) as generate:
                self.assertEqual(await entity.async_get_tts_audio("Hello", "en", {}), ("mp3", b"audio"))
            generate.assert_awaited_once_with(
                hass, provider_entity_id="tts.elevenlabs_text_to_speech", text="Hello",
                language="en", options={"voice": "declan-voice-id"},
            )
            cache.assert_called_once_with("jarvis_voice_cache")
            self.assertEqual(cache.return_value.get_or_generate_audio.call_args.kwargs["voice_id"], "v1:declan-voice-id")
