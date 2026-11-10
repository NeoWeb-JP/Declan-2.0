"""Configure the address and shared secret for the Declan test service."""
from urllib.parse import urlsplit

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import tts

from homeassistant.helpers import selector

from .voice_defaults import DEFAULT_PROVIDER


class DeclanTwoConfigFlow(config_entries.ConfigFlow, domain="declan_two"):
    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        return DeclanTwoOptionsFlow()

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


class DeclanTwoOptionsFlow(config_entries.OptionsFlowWithReload):
    async def async_step_init(self, user_input=None):
        current = self.config_entry.options
        errors = {}
        if user_input is not None:
            enabled = user_input["openai_stt_enabled"]
            key = user_input.get("openai_stt_api_key", "").strip() or current.get("openai_stt_api_key", "")
            host = user_input.get("wyoming_bridge_host", "").strip()
            provider = user_input.get("primary_tts", DEFAULT_PROVIDER).strip()
            if user_input.get("wyoming_bridge_enabled") and not host:
                errors["wyoming_bridge_host"] = "wyoming_host_required"
            if user_input.get("tts_enabled") and (
                not provider.startswith("tts.")
                or provider.startswith(("tts.jarvis_voice_manager", "tts.declan_voice_manager", "tts.declan_2_0_voice_manager"))
            ):
                errors["primary_tts"] = "invalid_tts_provider"
            if enabled and not key:
                errors["openai_stt_api_key"] = "openai_key_required"
            if not errors:
                return self.async_create_entry(title="", data={
                    **current,
                    **{key: value for key, value in user_input.items() if key != "openai_stt_api_key"},
                    "wyoming_bridge_host": host,
                    "primary_tts": provider,
                    "openai_stt_enabled": enabled,
                    "openai_stt_model": user_input["openai_stt_model"],
                    "openai_stt_api_key": key,
                })
        values = {**current, **(user_input or {})}
        schema = {
            vol.Required("openai_stt_enabled", default=values.get("openai_stt_enabled", False)): bool,
            vol.Required("openai_stt_model", default=values.get("openai_stt_model", "gpt-transcribe")):
                vol.In(["gpt-transcribe", "gpt-4o-mini-transcribe"]),
            vol.Optional("openai_stt_api_key"): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required("wyoming_bridge_enabled", default=values.get("wyoming_bridge_enabled", False)): bool,
            vol.Required("wyoming_bridge_host", default=values.get("wyoming_bridge_host", "")): str,
            vol.Required("wyoming_bridge_port", default=values.get("wyoming_bridge_port", 10300)):
                vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            vol.Required("tts_enabled", default=values.get("tts_enabled", False)): bool,
            vol.Required("primary_tts", default=values.get("primary_tts", DEFAULT_PROVIDER)): str,
            vol.Required("cache_enabled", default=values.get("cache_enabled", True)): bool,
            vol.Required("cache_revision", default=values.get("cache_revision", "v1")): vol.All(str, vol.Length(min=1)),
            vol.Required("category_fallback", default=values.get("category_fallback", True)): bool,
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
