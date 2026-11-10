"""Forward Assist text to the Declan 2.0 chat endpoint."""
import logging

import aiohttp
from homeassistant.components import conversation
from homeassistant.helpers import intent
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)


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
        error_reply = None
        speaker = getattr(user_input.text, "jarvis_speaker", None)
        speaker_data = {}
        if isinstance(speaker, tuple) and len(speaker) == 3:
            interaction_id, name, confidence = speaker
            if isinstance(interaction_id, str) and isinstance(name, str) and type(confidence) in (int, float) and 0 <= confidence <= 1:
                speaker_data = {"speaker": {"interaction_id": interaction_id, "name": name, "confidence": confidence}}
        elif hasattr(user_input.text, "jarvis_speaker"):
            speaker_data = {"speaker": {}}
        try:
            session = async_get_clientsession(self.hass)
            async with session.post(
                self._url,
                json={
                    "message": user_input.text,
                    "session_id": session_id,
                    "device_id": user_input.device_id,
                    "satellite_id": getattr(user_input, "satellite_id", None),
                    "user_id": user_input.context.user_id,
                    **speaker_data,
                },
                headers={"Authorization": f"Bearer {self._token}"},
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=75, sock_connect=3),
            ) as result:
                if result.status != 200:
                    _LOGGER.warning("Declan Assist request returned HTTP %s", result.status)
                    error_reply = ("Home Assistant couldn't authenticate with Declan."
                                   if result.status in {401, 403} else "Declan couldn't process that request.")
                else:
                    payload = await result.json()
                    if not isinstance(payload["reply"], str) or not isinstance(payload["session_id"], str):
                        raise ValueError("Invalid Declan response")
                    response.async_set_speech(payload["reply"])
                    session_id = payload["session_id"]
        except TimeoutError:
            _LOGGER.warning("Declan Assist request timed out")
            error_reply = "Declan took too long to respond. The command may still have run."
        except (aiohttp.ClientError, ValueError, TypeError, KeyError) as error:
            _LOGGER.warning("Declan Assist response failed: %s", type(error).__name__)
            error_reply = "I didn't get a usable reply from Declan."
        if error_reply:
            response.async_set_error(
                intent.IntentResponseErrorCode.FAILED_TO_HANDLE,
                error_reply,
            )
        return conversation.ConversationResult(response=response, conversation_id=session_id)
