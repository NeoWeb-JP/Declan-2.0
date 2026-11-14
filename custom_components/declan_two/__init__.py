"""Expose the standalone Declan service as a separate Assist agent."""

import logging

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession


from .capabilities_view import DeclanCapabilitiesView
from .history_view import DeclanHistoryView
from .chat_view import DeclanChatView

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["conversation", "stt", "tts"]


async def async_setup(hass, config):
    """Register the authenticated API route once per HA integration."""
    hass.http.register_view(DeclanCapabilitiesView())
    hass.http.register_view(DeclanHistoryView())
    hass.http.register_view(DeclanChatView())
    from .native_panel import async_register_native_panel
    await async_register_native_panel(hass)
    return True


async def async_setup_entry(hass, entry):
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def record_assist_reply(event):
        message = event.data.get("message")
        reply = event.data.get("reply")
        if not all(isinstance(value, str) and 0 < len(value.strip()) <= 1000 for value in (message, reply)):
            return
        try:
            async with async_get_clientsession(hass).post(
                entry.data["url"] + "/api/assist/history",
                json={
                    "message": message,
                    "reply": reply,
                    "session_id": event.data.get("session_id"),
                    "outcome": event.data.get("outcome"),
                    "routine_status": event.data.get("routine_status"),
                    "steps": event.data.get("steps"),
                },
                headers={"Authorization": f"Bearer {entry.data['token']}"},
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=3),
            ) as response:
                if response.status != 200:
                    _LOGGER.warning("Declan could not save a Home Assistant sentence reply (HTTP %s)", response.status)
        except (aiohttp.ClientError, TimeoutError):
            _LOGGER.warning("Declan could not save a Home Assistant sentence reply")

    entry.async_on_unload(hass.bus.async_listen("declan_two_assist_reply", record_assist_reply))
    return True


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
