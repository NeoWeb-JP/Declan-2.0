"""Forward Assist text to the Declan 2.0 chat endpoint."""
import aiohttp
from homeassistant.components import conversation
from homeassistant.helpers import intent
from homeassistant.helpers.aiohttp_client import async_get_clientsession


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([DeclanTwoAgent(entry)])


class DeclanTwoAgent(conversation.ConversationEntity):
    _attr_name = "Declan 2.0"

    def __init__(self, entry):
        self._attr_unique_id = entry.entry_id
        self._url = entry.data["url"] + "/api/assist"
        self._token = entry.data["token"]

    @property
    def supported_languages(self):
        return ["en"]

    async def async_process(self, user_input):
        response = intent.IntentResponse(language=user_input.language)
        session_id = user_input.conversation_id
        try:
            session = async_get_clientsession(self.hass)
            async with session.post(
                self._url,
                json={"message": user_input.text, "session_id": session_id},
                headers={"Authorization": f"Bearer {self._token}"},
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as result:
                if result.status != 200:
                    raise ValueError("Declan rejected the request")
                payload = await result.json()
            if not isinstance(payload["reply"], str) or not isinstance(payload["session_id"], str):
                raise ValueError("Invalid Declan response")
            response.async_set_speech(payload["reply"])
            session_id = payload["session_id"]
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError, KeyError):
            response.async_set_error(
                intent.IntentResponseErrorCode.FAILED_TO_HANDLE,
                "I couldn't reach the Declan 2.0 test service.",
            )
        return conversation.ConversationResult(response=response, conversation_id=session_id)
