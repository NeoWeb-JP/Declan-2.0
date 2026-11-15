"""Expose the standalone Declan service as a separate Assist agent."""

import logging
import re
from datetime import datetime, time

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
        # Only known safety categories can trigger overnight speech. Treat
        # unexpected values as noncritical rather than trusting free text.
        if not isinstance(kind, str):
            kind = "routine"
        # An arbitrary service caller must not be able to bypass quiet hours
        # by putting an unknown category into a free-text safety label.
        kind = kind.strip().lower()
        if kind not in {"security", "smoke", "carbon_monoxide", "critical_safety",
                        "routine", "dinner", "ev_reminder", "music"}:
            kind = "routine"
        # Use Home Assistant's configured household timezone rather than the
        # host/container timezone (often UTC, which differs during BST).
        zone_name = getattr(getattr(hass, "config", None), "time_zone", None)
        if isinstance(zone_name, str) and zone_name:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
            try:
                clock = datetime.now(ZoneInfo(zone_name)).time()
            except (ZoneInfoNotFoundError, ValueError, TypeError):
                # An invalid configured timezone makes overnight classification
                # unreliable. Fail closed rather than using the host's clock.
                _LOGGER.warning("Invalid Home Assistant timezone; suppressing announcement")
                return
        else:
            clock = datetime.now().astimezone().time()
        overnight = clock >= time(23) or clock < time(7)
        allowed = {"security", "smoke", "carbon_monoxide", "critical_safety"}
        if overnight and kind not in allowed:
            _LOGGER.info("Suppressed noncritical overnight announcement: %s", kind)
            return
        configured_outputs = entry.options.get("overnight_announcement_outputs", "")
        if not isinstance(configured_outputs, str):
            _LOGGER.warning("Declan overnight speaker configuration is invalid")
            return
        approved = {
            name.strip() for name in configured_outputs.split(",") if name.strip()
        }
        destination = call.data.get("entity_id", "")
        # Route announcements through Declan's own speech entity so quiet-hour
        # PCM attenuation applies without altering the Music Assistant volume.
        # Never bypass that policy by calling the raw upstream TTS provider.
        provider = ""
        if entry.options.get("tts_enabled", False):
            from homeassistant.helpers import entity_registry
            registry = entity_registry.async_get(hass)
            provider = registry.async_get_entity_id(
                "tts", "declan_two", f"{entry.entry_id}_voice_manager"
            ) or ""
            # A disabled or unavailable entity must not silently fall back
            # to an upstream TTS provider that bypasses quiet-hour handling.
            if provider:
                state = hass.states.get(provider) if hasattr(hass, "states") else None
                if state is not None and state.state in {"unavailable", "unknown"}:
                    provider = ""
        if not isinstance(destination, str) or not re.fullmatch(r"media_player\.[a-z0-9_]+", destination) or (
            overnight and destination not in approved
        ):
            _LOGGER.warning("Declan announcement destination is not approved: %s", destination)
            return
        if not isinstance(message, str) or not message.strip() or len(message) > 1000:
            _LOGGER.warning("Declan announcement message is empty or too long")
            return
        if not isinstance(provider, str) or not provider.startswith("tts."):
            _LOGGER.warning("Declan announcements require the Declan voice manager to be enabled")
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
