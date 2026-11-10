"""Test the bridge against a fake Home Assistant host and HTTP client."""

from importlib import import_module
from types import ModuleType, SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, Mock, patch


class AssistBridgeTests(IsolatedAsyncioTestCase):
    def setUp(self):
        class ConfigFlow:
            def __init_subclass__(cls, **kwargs):
                super().__init_subclass__()

        module_names = (
            "aiohttp", "voluptuous", "homeassistant", "homeassistant.helpers",
            "homeassistant.helpers.aiohttp_client", "homeassistant.components",
        )
        modules = {name: ModuleType(name) for name in module_names}
        modules["aiohttp"].ClientError = OSError
        modules["aiohttp"].ClientTimeout = Mock()
        modules["voluptuous"].Schema = Mock()
        modules["voluptuous"].Required = lambda name: name
        modules["homeassistant"].config_entries = SimpleNamespace(ConfigFlow=ConfigFlow)
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
