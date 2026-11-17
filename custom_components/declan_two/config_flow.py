"""Configure the address and shared secret for the Declan test service."""
import re

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import tts

from homeassistant.helpers import selector

from .config_validation import valid_declan_origin
from .voice_defaults import DEFAULT_PROVIDER


async def verify_declan_token(hass, url: str, token: str) -> str | None:
    """Check a Declan Assist token without redirects or leaking credentials."""
    try:
        async with async_get_clientsession(hass).get(
            url + "/api/capabilities",
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=5),
            allow_redirects=False,
        ) as response:
            if response.status in {401, 403}:
                return "invalid_auth"
            if response.status != 200:
                return "cannot_connect"
    except (aiohttp.ClientError, TimeoutError):
        return "cannot_connect"
    return None


# The audit environment lacks Home Assistant type definitions for ConfigFlow.__init_subclass__.
class DeclanTwoConfigFlow(config_entries.ConfigFlow, domain="declan_two"):  # type: ignore[call-arg]
    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        return DeclanTwoOptionsFlow()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            url = user_input["url"].strip().rstrip("/")
            valid = valid_declan_origin(url)
            if not valid:
                errors["url"] = "invalid_url"
            elif len(user_input["token"]) < 32:
                errors["token"] = "invalid_token"  # nosec B105 - HA validation error key, not a password
            else:
                auth_error = await verify_declan_token(self.hass, url, user_input["token"])
                if auth_error:
                    errors["base"] = auth_error
                if errors:
                    return self.async_show_form(
                        step_id="user", data_schema=vol.Schema({
                            vol.Required("url", default=url): str,
                            vol.Required("token"): selector.TextSelector(
                                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                            ),
                        }), errors=errors,
                    )
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


    async def async_step_reconfigure(self, user_input=None):
        """Allow updating the existing server URL and token without removing the entry."""
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            url = user_input["url"].strip().rstrip("/")
            token = user_input.get("token", "").strip() or entry.data["token"]
            if not valid_declan_origin(url):
                errors["url"] = "invalid_url"
            elif len(token) < 32:
                errors["token"] = "invalid_token"  # nosec B105 - HA form error key, not a credential
            else:
                auth_error = await verify_declan_token(self.hass, url, token)
                if auth_error:
                    errors["base"] = auth_error
                if not errors:
                    return self.async_update_reload_and_abort(
                        entry, data_updates={"url": url, "token": token},
                    )
        schema = vol.Schema({
            vol.Required("url", default=(user_input or {}).get("url", entry.data["url"])): str,
            vol.Optional("token"): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        })
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)


    async def async_step_reauth(self, entry_data):
        """Start reauthentication for an existing Declan config entry."""
        self._reauth_entry_data = entry_data
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Validate a replacement Assist token before updating the entry."""
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            token = user_input["token"].strip()
            if len(token) < 32:
                errors["token"] = "invalid_token"  # nosec B105 - HA form error identifier
            else:
                auth_error = await verify_declan_token(self.hass, entry.data["url"], token)
                if auth_error:
                    errors["base"] = auth_error
                if not errors:
                    return self.async_update_reload_and_abort(
                        entry, data_updates={"token": token},
                    )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({
                vol.Required("token"): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
            }),
            errors=errors,
        )


class DeclanTwoOptionsFlow(config_entries.OptionsFlowWithReload):
    async def async_step_init(self, user_input=None):
        current = self.config_entry.options
        errors = {}
        if user_input is not None:
            enabled = user_input["openai_stt_enabled"]
            key = user_input.get("openai_stt_api_key", "").strip() or current.get("openai_stt_api_key", "")
            host = user_input.get("wyoming_bridge_host", "").strip()
            local_stt = user_input.get('local_stt_entity', '').strip()
            if local_stt and not re.fullmatch(r'stt\.[a-z0-9_]+', local_stt):
                errors['local_stt_entity'] = 'invalid_stt_provider'
            provider = user_input.get("primary_tts", DEFAULT_PROVIDER).strip()
            if user_input.get("wyoming_bridge_enabled") and not host:
                errors["wyoming_bridge_host"] = "wyoming_host_required"
            if user_input.get("tts_enabled") and (
                not provider.startswith("tts.")
                or provider.startswith(("tts.jarvis_voice_manager", "tts.declan_voice_manager", "tts.declan_2_0_voice_manager"))
            ):
                errors["primary_tts"] = "invalid_tts_provider"
            destinations = user_input.get("overnight_announcement_outputs", "").strip()
            if destinations and any(
                not re.fullmatch(r"media_player\.[a-z0-9_]+", item.strip())
                for item in destinations.split(",")
            ):
                errors["overnight_announcement_outputs"] = "invalid_media_player"
            if enabled and not key:
                errors["openai_stt_api_key"] = "openai_key_required"
            if not errors:
                return self.async_create_entry(title="", data={
                    **current,
                    **{key: value for key, value in user_input.items() if key != "openai_stt_api_key"},
                    "wyoming_bridge_host": host,
                    "local_stt_entity": local_stt,
                    "primary_tts": provider,
                    "openai_stt_enabled": enabled,
                    "openai_stt_model": user_input["openai_stt_model"],
                    "openai_stt_api_key": key,
                })
        values = {**current, **(user_input or {})}
        schema = {
            vol.Required("openai_stt_enabled", default=values.get("openai_stt_enabled", False)): bool,
            vol.Required("openai_stt_model", default=values.get("openai_stt_model", "gpt-4o-mini-transcribe")):
                vol.In(["gpt-transcribe", "gpt-4o-mini-transcribe"]),
            vol.Optional("openai_stt_api_key"): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required("wyoming_bridge_enabled", default=values.get("wyoming_bridge_enabled", False)): bool,
            vol.Optional("local_stt_entity", default=values.get("local_stt_entity", "")): str,
            vol.Required("wyoming_bridge_host", default=values.get("wyoming_bridge_host", "")): str,
            vol.Required("wyoming_bridge_port", default=values.get("wyoming_bridge_port", 10300)):
                vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            vol.Required("tts_enabled", default=values.get("tts_enabled", False)): bool,
            vol.Required("primary_tts", default=values.get("primary_tts", DEFAULT_PROVIDER)): str,
            vol.Required("cache_enabled", default=values.get("cache_enabled", True)): bool,
            vol.Required("cache_revision", default=values.get("cache_revision", "v1")): vol.All(str, vol.Length(min=1)),
            vol.Required("category_fallback", default=values.get("category_fallback", True)): bool,
            vol.Optional("overnight_announcement_outputs",
                         default=values.get("overnight_announcement_outputs", "")): str,
            vol.Required("primary_daily_character_limit", default=values.get("primary_daily_character_limit", 0)):
                vol.All(vol.Coerce(int), vol.Range(min=0, max=10_000_000)),
        }
        voices = {"": "Use the voice configured in the provider"}
        try:
            engine = tts.get_engine_instance(self.hass, values.get("primary_tts", DEFAULT_PROVIDER))
            if engine is not None:
                voices.update({v.voice_id: v.name for v in engine.async_get_supported_voices("en") or []})
        except (LookupError, AttributeError, ValueError):
            pass
        selected_voice = values.get("elevenlabs_voice", "")
        if selected_voice:
            voices.setdefault(selected_voice, selected_voice)
        schema[vol.Required("elevenlabs_voice", default=selected_voice)] = vol.In(voices)
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema), errors=errors)
