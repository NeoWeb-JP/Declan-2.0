"""FUT-60: Settings -> Household -> Guest tone. Guests hear Declan's Home sass by default."""
import importlib.util
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

from declan.http import settings_read_routes
from declan.turn import household_settings, personality, personality_policy, roast
from declan.voice import settings_voice_post

ROOT = Path(__file__).resolve().parents[1]


class TemporarySettings(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.object(household_settings, "PATH", Path(folder) / "household-settings.json"))
        self.enterContext(patch.dict(os.environ, {}, clear=True))

    def polite(self):
        household_settings.save({"guest_tone": "polite"})


class SettingsTests(TemporarySettings):
    def test_default_is_home_then_environment_then_saved(self):
        self.assertEqual(household_settings.listing(),
                         {"settings": {"guest_tone": "home", "shelve_days": 3, "fresh_lines": True},
                          "sources": dict.fromkeys(("guest_tone", "shelve_days", "fresh_lines"), "default")})
        with patch.dict(os.environ, {"DECLAN_GUEST_TONE": " Polite "}):
            self.assertEqual(household_settings.guest_tone(), "polite")
            self.assertEqual(household_settings.listing()["sources"]["guest_tone"], "environment")
            saved = household_settings.save({"guest_tone": "home"})
        self.assertEqual(saved["settings"]["guest_tone"], "home")
        self.assertEqual(saved["sources"]["guest_tone"], "saved")

    def test_invalid_payloads_and_files_are_rejected(self):
        for payload in (None, {}, {"guest_tone": "rude"}, {"guest_tone": "home", "x": 1}, {"guest_tone": 1}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                household_settings.save(payload)
        household_settings.PATH.write_text(json.dumps({"guest_tone": "nope"}))
        self.assertEqual(household_settings.guest_tone(), "home")
        household_settings.PATH.write_text("not json")
        self.assertEqual(household_settings.guest_tone(), "home")

    def test_guest_lines_only_for_guests_with_the_polite_tone(self):
        self.assertFalse(household_settings.guest_lines(True))
        self.polite()
        self.assertTrue(household_settings.guest_lines(True))
        self.assertFalse(household_settings.guest_lines(False))


class HomeToneTests(TemporarySettings):
    """Default tone: guests and visitors get exactly the household's lines."""

    def test_persona_stays_home_with_guests_and_visitors(self):
        for guest_mode, visitors in (("on", False), ("off", True), ("off", None)):
            with self.subTest(guest_mode=guest_mode, visitors=visitors):
                self.assertEqual(personality_policy.response_guest_mode(guest_mode, visitors), "off")
        self.polite()
        self.assertEqual(personality_policy.response_guest_mode("on", False), "on")

    def test_routine_replies_use_home_lines_for_guests(self):
        home = {personality_policy.household_language.render(line)
                for line in personality_policy._NIGHT_HOME}
        reply = personality_policy.night_request_reply(guest=True, visitor_present=True)
        self.assertIn(reply.removeprefix("Good night. "), home)
        sexy = {personality_policy.household_language.render(line)
                for line in personality_policy._SEXY_HOME["start"]}
        self.assertIn(personality_policy.sexy_request_reply("start", guest=True), sexy)

    def test_decorate_roasts_guests_like_the_household(self):
        savage = {personality_policy.household_language.render(line) for line in personality_policy._SAVAGE}
        reply = personality_policy.decorate("Done.", outcome="confirmed", guest=True, visitor_present=None)
        self.assertIn(reply.removeprefix("Done. "), savage)
        # Failures are never decorated, whatever the tone.
        self.assertEqual(personality_policy.decorate("Failed.", outcome="failed", guest=True), "Failed.")

    def test_command_lines_and_roasts_use_home_lines(self):
        with patch("declan.turn.command_responses.selected", return_value=None):
            line = personality.choose_line("weather", "on")
        self.assertIn(line, {personality.household_language.render(text)
                             for text in personality.LINES["weather"][False]})
        self.assertEqual(personality_policy.response_guest_mode("on", False), "off")
        self.assertIn(roast.respond("Mike", guest=False).replace("Mike", "{name}"), roast.HOME)

    def test_polite_tone_restores_guest_lines(self):
        self.polite()
        guest = {personality_policy.household_language.render(line)
                 for line in personality_policy._NIGHT_GUEST}
        reply = personality_policy.night_request_reply(guest=True)
        self.assertIn(reply.removeprefix("Good night. "), guest)
        with patch("declan.turn.command_responses.selected", return_value=None):
            line = personality.choose_line("weather", "on")
        self.assertIn(line, {personality.household_language.render(text)
                             for text in personality.LINES["weather"][True]})


class RouteTests(TemporarySettings):
    def test_read_and_save_routes_and_gates(self):
        handler = SimpleNamespace(path="/api/settings/household", sent=[])
        handler.send_json = lambda status, payload: handler.sent.append((status, payload))
        self.assertTrue(settings_read_routes.handles(handler.path))
        settings_read_routes.dispatch(handler, voicepipeline=None, voice_profiles=None, diagnostics=None,
                                      history=None, ai_budget=None, ai_settings=None, ai_credentials=None,
                                      spotify_playlists=None)
        self.assertEqual(handler.sent[-1][1]["settings"]["guest_tone"], "home")
        names = ("spotify_save", "ai_replace_key", "ai_save", "ai_configured", "music", "spotify_playlists",
                 "playlist_handler", "opener_factory", "voice_manage", "pipeline_error", "profiles_manage",
                 "preview", "apply")
        for body, status in (({"settings": {"guest_tone": "polite"}}, 200),
                             ({"settings": {"guest_tone": "x"}}, 400), ({}, 400)):
            settings_voice_post.dispatch(handler, body, **dict.fromkeys(names))
            self.assertEqual(handler.sent[-1][0], status)
        self.assertEqual(household_settings.guest_tone(), "polite")
        for module in ("get_access_gate_http", "post_route_gate_http", "post_origin_auth_http"):
            self.assertIn('"/api/settings/household"', (ROOT / "declan/http" / f"{module}.py").read_text())


def load_view():
    web = SimpleNamespace(json_response=lambda payload, status=200, headers=None: {"payload": payload, "status": status})
    aiohttp = SimpleNamespace(web=web, ClientTimeout=lambda total: total, ClientError=OSError)
    session = MagicMock()
    with patch.dict("sys.modules", {
        "aiohttp": aiohttp, "homeassistant": SimpleNamespace(), "homeassistant.components": SimpleNamespace(),
        "homeassistant.components.http": SimpleNamespace(HomeAssistantView=object),
        "homeassistant.helpers": SimpleNamespace(),
        "homeassistant.helpers.aiohttp_client": SimpleNamespace(async_get_clientsession=lambda hass: session),
    }):
        spec = importlib.util.spec_from_file_location(
            "household_view_fixture", ROOT / "custom_components/declan_two/household_view.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module, session


class ViewAndPanelTests(unittest.IsolatedAsyncioTestCase):
    async def test_view_validates_relays_and_remembers_the_tone(self):
        module, session = load_view()
        response = MagicMock(status=200)
        sources = dict.fromkeys(("guest_tone", "shelve_days", "fresh_lines"), "saved")
        response.json = AsyncMock(return_value={"settings": {"guest_tone": "polite", "shelve_days": 3, "fresh_lines": True},
                                                "sources": sources, "generated": None})
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=response)
        context.__aexit__ = AsyncMock(return_value=False)
        session.get.return_value = session.post.return_value = context
        entry = SimpleNamespace(data={"url": "http://declan", "token": "t" * 40})
        hass = SimpleNamespace(data={}, config_entries=SimpleNamespace(async_entries=lambda domain: [entry]))

        def request(user, body):
            class Request(dict):
                app: ClassVar[dict] = {"hass": hass}
                content_length = 40
                content_type = "application/json"

                async def json(self):
                    return body
            return Request(hass_user=user)
        admin = SimpleNamespace(is_admin=True)
        view = module.DeclanHouseholdView()
        self.assertEqual(module.guest_tone(hass), "home")
        self.assertEqual((await view.get(request(SimpleNamespace(is_admin=False), None)))["status"], 403)
        bodies: tuple[object, ...] = ({"settings": {"guest_tone": "rude"}}, [1], {"x": 1}, {"settings": {}})
        for body in bodies:
            self.assertEqual((await view.post(request(admin, body)))["status"], 400)
        result = await view.post(request(admin, {"settings": {"guest_tone": "polite"}}))
        self.assertEqual(result["status"], 200)
        self.assertEqual(module.guest_tone(hass), "polite")
        response.json.return_value = {"settings": {"guest_tone": "nope", "shelve_days": 3, "fresh_lines": True},
                                      "sources": sources}
        self.assertEqual((await view.get(request(admin, None)))["status"], 502)
        response.json.return_value = {"settings": {"guest_tone": "home", "shelve_days": 3, "fresh_lines": True},
                                      "sources": sources,
                                      "generated": {"lines": [{"key": "roast:home", "line": "Eish.", "created": 1.0}],
                                                    "spent_micro_usd": 10, "budget_micro_usd": 1000000}}
        self.assertEqual(len((await view.get(request(admin, None)))["payload"]["generated"]["lines"]), 1)
        # Saving only some keys (an older panel) is allowed; bad values are not.
        for body in ({"settings": {"guest_tone": "home", "shelve_days": 31}},
                     {"settings": {"guest_tone": "home", "fresh_lines": "yes"}},
                     {"delete_line": {"key": "roast:home"}}):
            self.assertEqual((await view.post(request(admin, body)))["status"], 400)
        response.json.return_value = {"deleted": True}
        deleted = await view.post(request(admin, {"delete_line": {"key": "roast:home", "line": "Eish."}}))
        self.assertEqual(deleted["payload"], {"deleted": True})
        response.json.return_value = {"settings": {"guest_tone": "home", "shelve_days": 3, "fresh_lines": True},
                                      "sources": sources}
        await module.refresh(hass, entry)
        self.assertEqual(module.guest_tone(hass), "home")

    def test_panel_and_integration_are_wired(self):
        js = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()
        for needle in ("declan_two/household", "loadHousehold()", "saveHousehold()", 'class="household-form"',
                       'name="guest_tone"', "settings-section--household", 'name="shelve_days"',
                       'name="fresh_lines"', "renderFreshLines(", "delete_line"):
            self.assertIn(needle, js)
        init = (ROOT / "custom_components/declan_two/__init__.py").read_text()
        self.assertIn("DeclanHouseholdView()", init)
        self.assertIn("refresh_household(hass, entry)", init)
        tts = (ROOT / "custom_components/declan_two/tts.py").read_text()
        self.assertIn('guest_tone(self.hass) == "polite"', tts)


if __name__ == "__main__":
    unittest.main()
