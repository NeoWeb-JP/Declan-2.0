"""Music behaviour settings: saved value > environment > default, editable from the panel."""
import importlib.util
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from declan.music import media_settings_post, music, music_settings
from declan.http import settings_read_routes

ROOT = Path(__file__).resolve().parents[1]


class StoreTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(TemporaryDirectory())
        self.path = Path(folder) / "music-settings.json"
        self.enterContext(patch.dict(os.environ, {}, clear=True))

    def test_defaults_are_reply_first_on_and_music_assistant_search_off(self):
        self.assertEqual(music_settings.listing(self.path), {
            "settings": {"reply_first": True, "music_assistant_search": False},
            "sources": {"reply_first": "default", "music_assistant_search": "default"},
            "start_volume": {"percent": 30, "source": "default"}})

    def test_environment_applies_until_a_value_is_saved(self):
        with patch.dict(os.environ, {"DECLAN_MUSIC_REPLY_FIRST": "0", "DECLAN_MUSIC_ASSISTANT_SEARCH": "yes"}):
            self.assertEqual(music_settings.listing(self.path)["settings"],
                             {"reply_first": False, "music_assistant_search": True})
            self.assertEqual(set(music_settings.listing(self.path)["sources"].values()), {"environment"})
            saved = music_settings.save(self.path, {"reply_first": True, "music_assistant_search": False})
            self.assertEqual(saved["settings"], {"reply_first": True, "music_assistant_search": False})
            self.assertEqual(set(saved["sources"].values()), {"saved"})
            self.assertTrue(music_settings.enabled(self.path, "reply_first"))
            self.assertFalse(music_settings.enabled(self.path, "music_assistant_search"))

    def test_invalid_payloads_are_rejected_and_nothing_is_written(self):
        payloads: tuple[object, ...] = (None, [], {}, {"reply_first": True},
                        {"reply_first": 1, "music_assistant_search": False},
                                        {"reply_first": True, "music_assistant_search": False, "extra": True})
        for payload in payloads:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                music_settings.save(self.path, payload)
        self.assertFalse(self.path.exists())

    def test_corrupt_or_partial_file_falls_back_per_setting(self):
        self.path.write_text("not json")
        self.assertTrue(music_settings.enabled(self.path, "reply_first"))
        self.path.write_text(json.dumps({"music_assistant_search": True, "reply_first": "no"}))
        listing = music_settings.listing(self.path)
        self.assertEqual(listing["settings"], {"reply_first": True, "music_assistant_search": True})
        self.assertEqual(listing["sources"], {"reply_first": "default", "music_assistant_search": "saved"})

    def test_music_module_reads_the_saved_settings(self):
        with patch.object(music, "SPOTIFY_SETTINGS", self.path.with_name("spotify-settings.json")):
            self.assertEqual(music.music_settings_path(), self.path)
            music_settings.save(self.path, {"reply_first": False, "music_assistant_search": True})
            self.assertFalse(music.reply_first_enabled())
            self.assertTrue(music.music_assistant_search_enabled())


class Handler:
    def __init__(self, path):
        self.path = path
        self.sent = []

    def send_json(self, status, payload):
        self.sent.append((status, payload))


class RouteTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.object(music, "SPOTIFY_SETTINGS", Path(folder) / "spotify-settings.json"))
        self.enterContext(patch.dict(os.environ, {}, clear=True))

    def post(self, body):
        handler = Handler("/api/settings/music")
        self.assertTrue(media_settings_post.handles(handler.path))
        media_settings_post.dispatch(handler, body, music=music, spotify_playlists=None,
                                     playlist_handler=None, opener_factory=None)
        return handler.sent[-1]

    def test_get_and_post_round_trip(self):
        handler = Handler("/api/settings/music")
        self.assertTrue(settings_read_routes.handles(handler.path))
        settings_read_routes.dispatch(handler, voicepipeline=None, voice_profiles=None, diagnostics=None,
                                      history=None, ai_budget=None, ai_settings=None, ai_credentials=None,
                                      spotify_playlists=None)
        self.assertEqual(handler.sent[-1][0], 200)
        self.assertEqual(handler.sent[-1][1]["settings"]["reply_first"], True)
        status, payload = self.post({"settings": {"reply_first": False, "music_assistant_search": True}})
        self.assertEqual(status, 200)
        self.assertEqual(payload["sources"], {"reply_first": "saved", "music_assistant_search": "saved"})
        self.assertTrue(music.music_assistant_search_enabled())

    def test_start_volume_is_saved_with_the_switches(self):
        status, payload = self.post({"settings": {"reply_first": True, "music_assistant_search": False},
                                     "start_volume": 25})
        self.assertEqual(status, 200)
        self.assertEqual(payload["start_volume"], {"percent": 25, "source": "saved"})
        self.assertEqual(music.start_volume(), 0.25)
        for bad in (101, "25", 2.5):
            with self.subTest(bad=bad):
                self.assertEqual(self.post({"settings": {"reply_first": True, "music_assistant_search": False},
                                            "start_volume": bad})[0], 400)

    def test_bad_posts_are_400(self):
        for body in (None, {}, {"settings": {"reply_first": "yes", "music_assistant_search": False}},
                     {"settings": {"reply_first": True, "music_assistant_search": False}, "x": 1}):
            with self.subTest(body=body):
                self.assertEqual(self.post(body)[0], 400)

    def test_route_is_on_every_gate_allowlist(self):
        for module in ("get_access_gate_http", "post_route_gate_http", "post_origin_auth_http"):
            with self.subTest(module=module):
                self.assertIn('"/api/settings/music"', (ROOT / "declan/http" / f"{module}.py").read_text())


class ViewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        web = SimpleNamespace(json_response=lambda payload, status=200, headers=None:
                              {"payload": payload, "status": status, "headers": headers})
        aiohttp = SimpleNamespace(web=web, ClientTimeout=lambda total: total, ClientError=OSError)
        self.enterContext(patch.dict("sys.modules", {
            "aiohttp": aiohttp, "homeassistant": SimpleNamespace(), "homeassistant.components": SimpleNamespace(),
            "homeassistant.components.http": SimpleNamespace(HomeAssistantView=object),
            "homeassistant.helpers": SimpleNamespace(),
            "homeassistant.helpers.aiohttp_client": SimpleNamespace(async_get_clientsession=lambda hass: None),
        }))
        path = ROOT / "custom_components/declan_two/music_settings_view.py"
        spec = importlib.util.spec_from_file_location("music_settings_view_fixture", path)
        assert spec is not None and spec.loader is not None
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.view = self.module.DeclanMusicSettingsView()

    def request(self, user, body=None, content_type="application/json"):
        raw = json.dumps(body).encode() if body is not None else b""

        class Request(dict):
            app = {"hass": SimpleNamespace(config_entries=SimpleNamespace(async_entries=lambda domain: []))}
            content_length = len(raw) or None

            async def json(self):
                return body
        request = Request(hass_user=user)
        request.content_type = content_type  # type: ignore[attr-defined]
        return request

    async def test_non_admin_is_refused(self):
        result = await self.view.get(self.request(SimpleNamespace(is_admin=False)))
        self.assertEqual(result["status"], 403)

    async def test_post_validates_before_relaying(self):
        admin = SimpleNamespace(is_admin=True)
        for body in ({"settings": {"reply_first": "1", "music_assistant_search": False}},
                     {"settings": {"reply_first": True}}, {"other": 1}):
            with self.subTest(body=body):
                self.assertEqual((await self.view.post(self.request(admin, body)))["status"], 400)
        for start_volume in (101, -1, "30", 2.5, True):
            bad_volume: dict[str, object] = {"settings": {"reply_first": True, "music_assistant_search": True},
                                             "start_volume": start_volume}
            with self.subTest(start_volume=start_volume):
                self.assertEqual((await self.view.post(self.request(admin, bad_volume)))["status"], 400)
        with_volume = {"settings": {"reply_first": True, "music_assistant_search": True}, "start_volume": 30}
        self.assertEqual((await self.view.post(self.request(admin, with_volume)))["status"], 503)
        good = {"settings": {"reply_first": True, "music_assistant_search": True}}
        # Valid body reaches the relay, which reports the missing config entry.
        self.assertEqual((await self.view.post(self.request(admin, good)))["status"], 503)

    def test_start_volume_from_the_backend_is_validated(self):
        self.assertTrue(self.module.valid_start_volume({"percent": 30, "source": "default"}))
        for value in (None, {"percent": 130, "source": "default"}, {"percent": 30, "source": "x"},
                      {"percent": "30", "source": "saved"}, {"percent": 30}):
            with self.subTest(value=value):
                self.assertFalse(self.module.valid_start_volume(value))

    def test_view_is_registered_and_panel_is_wired(self):
        init = (ROOT / "custom_components/declan_two/__init__.py").read_text()
        self.assertIn("DeclanMusicSettingsView()", init)
        js = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()
        for needle in ("declan_two/music-settings", "loadMusicSettings()", "saveMusicSettings()",
                       'name="reply_first"', 'name="music_assistant_search"', "settings-section--music"):
            self.assertIn(needle, js)
        self.assertNotIn("Bearer ", js)


if __name__ == "__main__":
    unittest.main()
