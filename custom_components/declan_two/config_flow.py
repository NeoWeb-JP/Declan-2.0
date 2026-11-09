"""Configure the address and shared secret for the Declan test service."""
from urllib.parse import urlsplit

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector


class DeclanTwoConfigFlow(config_entries.ConfigFlow, domain="declan_two"):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            url = user_input["url"].strip().rstrip("/")
            try:
                parsed = urlsplit(url)
                valid = (parsed.scheme in {"http", "https"} and parsed.hostname
                         and not any((parsed.username, parsed.password, parsed.query, parsed.fragment)))
            except ValueError:
                valid = False
            if not valid:
                errors["url"] = "invalid_url"
            elif len(user_input["token"]) < 32:
                errors["token"] = "invalid_token"
            else:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Declan 2.0", data={"url": url, "token": user_input["token"]}
                )
        schema = vol.Schema({
            vol.Required("url"): str,
            vol.Required("token"): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
