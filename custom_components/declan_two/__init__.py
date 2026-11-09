"""Expose the standalone Declan service as a separate Assist agent."""


async def async_setup_entry(hass, entry):
    await hass.config_entries.async_forward_entry_setups(entry, ["conversation"])
    return True


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, ["conversation"])
