"""Declan 2.0 Running: is the Declan service up and answering Home Assistant?

After a power cut Declan's container can fail to start without anyone noticing.
This sensor asks Declan every 30 seconds (the same token-checked capabilities call
the panel uses). It is on only when Declan answers with HTTP 200, so a stopped
container, a crashed service or a broken token all show as off. Pair it with the
shipped automation (home_assistant/declan_down_alert.automation.yaml) to get a
phone alert. The alert can't use Declan's own voice: if he's down, so is his TTS.
"""
from datetime import UTC, datetime, timedelta

import aiohttp
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.aiohttp_client import async_get_clientsession

SCAN_INTERVAL = timedelta(seconds=30)
PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([DeclanRunningSensor(hass, entry)], update_before_add=True)


def describe_failure(status=None, error=None):
    """A short, plain reason for the attributes (and the alert text)."""
    if status in (401, 403):
        return f"Declan answered but refused the token (HTTP {status}); check the integration's token"
    if status is not None:
        return f"Declan answered with HTTP {status}"
    if isinstance(error, TimeoutError):
        return "No answer within 5 seconds"
    return "Can't reach Declan (container or service not running?)"


class DeclanRunningSensor(BinarySensorEntity):
    _attr_name = "Declan 2.0 Running"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:robot-happy"
    _attr_should_poll = True

    def __init__(self, hass, entry):
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_running"
        self._attr_is_on = None
        self._attr_extra_state_attributes = {"version": None, "last_seen": None, "problem": None, "url": entry.data["url"]}

    async def async_update(self):
        attributes = dict(self._attr_extra_state_attributes)
        status = error = None
        try:
            async with async_get_clientsession(self.hass).get(
                self._entry.data["url"] + "/api/capabilities",
                headers={"Authorization": f"Bearer {self._entry.data['token']}"},
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                status = response.status
                payload = await response.json(content_type=None) if status == 200 else None
        except (aiohttp.ClientError, TimeoutError, ValueError) as caught:
            error = caught
            payload = None
        if status == 200:
            version = payload.get("server_version") if isinstance(payload, dict) else None
            attributes.update(version=version if isinstance(version, str) else None,
                              last_seen=datetime.now(UTC).isoformat(timespec="seconds"), problem=None)
            self._attr_is_on = True
        else:
            attributes["problem"] = describe_failure(status, error)
            self._attr_is_on = False
        self._attr_extra_state_attributes = attributes
