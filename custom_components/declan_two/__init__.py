"""Expose the standalone Declan service as a separate Assist agent."""

import logging

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession


from .capabilities_view import DeclanCapabilitiesView
from .history_view import DeclanHistoryView
from .chat_view import DeclanChatView
from .media_players_view import DeclanMediaPlayersView
from .music_playlists_view import DeclanMusicPlaylistsView
from .ai_settings_view import DeclanAISettingsView
from .voice_review_view import DeclanVoiceReviewView
from .updates_view import DeclanUpdatesView
from .microphone_view import DeclanMicrophoneView
from .settings_status_view import DeclanSettingsStatusView
from .management_view import DeclanManagementView

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["conversation", "stt", "tts"]


async def async_setup(hass, config):
    """Register the authenticated API route once per HA integration."""
    hass.http.register_view(DeclanCapabilitiesView())
    hass.http.register_view(DeclanHistoryView())
    hass.http.register_view(DeclanChatView())
    hass.http.register_view(DeclanMediaPlayersView())
    hass.http.register_view(DeclanMusicPlaylistsView())
    hass.http.register_view(DeclanAISettingsView())
    hass.http.register_view(DeclanVoiceReviewView())
    hass.http.register_view(DeclanUpdatesView())
    hass.http.register_view(DeclanMicrophoneView())
    hass.http.register_view(DeclanSettingsStatusView())
    hass.http.register_view(DeclanManagementView())
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

    # Central gate for unsolicited speech. Home Assistant automations can
    # invoke declan_two.announce, but never bypass the overnight allowlist.
    async def announce(call):
        kind = call.data.get("kind", "routine")
        message = call.data.get("message", "")
        clock = datetime.now().astimezone().time()
        overnight = clock >= time(23) or clock < time(7)
        allowed = {"security", "smoke", "carbon_monoxide", "critical_safety"}
        if overnight and kind not in allowed:
            _LOGGER.info("Suppressed noncritical overnight announcement: %s", kind)
            return
        approved = {
            name.strip() for name in entry.options.get(
                "overnight_announcement_outputs", "").split(",") if name.strip()
        }
        destination = call.data.get("entity_id", "")
        provider = entry.options.get("primary_tts", "")
        if not isinstance(destination, str) or not destination.startswith("media_player.") or (
            overnight and destination not in approved
        ):
            _LOGGER.warning("Declan announcement destination is not approved: %s", destination)
            return
        if not isinstance(message, str) or not message.strip():
            return
        if not isinstance(provider, str) or not provider.startswith("tts."):
            _LOGGER.warning("Declan announcement has no configured TTS provider")
            return
        await hass.services.async_call(
            "tts", "speak",
            {"entity_id": provider,
             "media_player_entity_id": destination,
             "message": message},
            blocking=True,
        )

    hass.services.async_register("declan_two", "announce", announce)
    entry.async_on_unload(lambda: hass.services.async_remove("declan_two", "announce"))

    entry.async_on_unload(hass.bus.async_listen("declan_two_assist_reply", record_assist_reply))
    return True


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
