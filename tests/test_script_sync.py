"""FUT-62: HA script sync. HA is master; nothing is written without a confirmed request."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from typing import ClassVar
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components/declan_two"


def load(name):
    spec = importlib.util.spec_from_file_location(f"declan_two_fixture.{name}", COMPONENT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sync = load("script_sync")
A = {"alias": "Declan - Good Night", "sequence": [{"action": "light.turn_off", "target": {"entity_id": "light.x"}}]}
A_REFORMATTED = {"alias": "Declan - Good Night",
                 "sequence": [{"action": "light.turn_off", "target": {"entity_id": "light.x"}}]}
B = {"alias": "Declan - Good Night", "sequence": [{"action": "light.turn_off", "target": {"entity_id": "light.y"}}]}
C = {"alias": "Declan - Good Night", "sequence": []}


class LogicTests(unittest.TestCase):
    def test_formatting_only_differences_are_in_sync(self):
        folded = {"alias": "x", "wait_template": "{{ a\n   and b }}\n"}
        flat = {"alias": "x", "wait_template": "{{ a and b }}"}
        self.assertEqual(sync.fingerprint(folded), sync.fingerprint(flat))
        self.assertEqual(sync.state(A, A_REFORMATTED, None), "in_sync")

    def test_states(self):
        base = {"repo": sync.fingerprint(A), "ha": sync.fingerprint(A)}
        self.assertEqual(sync.state(A, None, base), "missing")
        self.assertEqual(sync.state(A, B, base), "ha_changed")        # HA edited, repo not
        self.assertEqual(sync.state(B, A, base), "repo_changed")      # release changed, HA not
        self.assertEqual(sync.state(B, C, base), "both_changed")
        self.assertEqual(sync.state(A, B, None), "different")         # no earlier sync

    def test_matching_by_alias_then_slug(self):
        live = {"my_night": "declan - good night", "other": "Something else"}
        self.assertEqual(sync.object_id("Declan - Good Night", live), "my_night")
        self.assertEqual(sync.object_id("Declan - Sexy Time Controller", live), "declan_sexy_time_controller")

    def test_report_and_merge(self):
        rows = sync.report({"good_night.script.yaml": ("Declan - Good Night", A)},
                           {"declan_good_night": ("Declan - Good Night", B)},
                           {"good_night.script.yaml": {"repo": sync.fingerprint(A), "ha": sync.fingerprint(A)}})
        self.assertEqual([(row["entity_id"], row["state"]) for row in rows],
                         [("script.declan_good_night", "ha_changed")])
        self.assertEqual(sync.merge_script({"keep": {"alias": "k"}}, "new", A), {"keep": {"alias": "k"}, "new": A})
        self.assertEqual(sync.merge_script(None, "new", A), {"new": A})
        with self.assertRaises(ValueError):
            sync.merge_script(["not", "a", "mapping"], "new", A)
        self.assertIn("+++ home-assistant/x", sync.unified_diff("a: 1\n", "a: 2\n", "x"))

    def test_shipped_scripts_match_the_repo_copies(self):
        shipped = sorted(path.name for path in (COMPONENT / "declan_scripts").glob("*.script.yaml"))
        self.assertEqual(shipped, sorted(path.name for path in (ROOT / "home_assistant").glob("*.script.yaml")))
        for name in shipped:
            with self.subTest(name=name):
                self.assertEqual((COMPONENT / "declan_scripts" / name).read_text(),
                                 (ROOT / "home_assistant" / name).read_text())


def stub_modules():
    """Minimal aiohttp/HA stand-ins: YAML is JSON here, storage is in memory."""
    web = SimpleNamespace(json_response=lambda payload, status=200, headers=None: {"payload": payload, "status": status},
                          HTTPForbidden=type("HTTPForbidden", (Exception,), {}))
    ha_yaml = SimpleNamespace(parse_yaml=json.loads, dump=lambda value: json.dumps(value, sort_keys=True, indent=1))

    class Store:
        saved: ClassVar[dict] = {}

        def __init__(self, hass, version, key):
            self.key = key

        async def async_load(self):
            return dict(Store.saved)

        async def async_save(self, data):
            Store.saved = dict(data)
    util = ModuleType("homeassistant.util")
    util.yaml = ha_yaml  # type: ignore[attr-defined]
    return {"aiohttp": SimpleNamespace(web=web), "homeassistant": SimpleNamespace(),
            "homeassistant.components": SimpleNamespace(),
            "homeassistant.components.http": SimpleNamespace(HomeAssistantView=object),
            "homeassistant.util": util, "homeassistant.util.yaml": ha_yaml,
            "homeassistant.helpers": SimpleNamespace(),
            "homeassistant.helpers.storage": SimpleNamespace(Store=Store)}, Store


class ViewTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        modules, self.Store = stub_modules()
        self.enterContext(patch.dict("sys.modules", modules))
        sys.modules["declan_two_fixture"] = ModuleType("declan_two_fixture")
        sys.modules["declan_two_fixture"].__path__ = []  # type: ignore[attr-defined]
        sys.modules["declan_two_fixture.script_sync"] = sync
        self.view_module = load("script_sync_view")
        folder = Path(self.enterContext(TemporaryDirectory()))
        self.scripts = folder / "declan_scripts"
        self.scripts.mkdir()
        (self.scripts / "good_night.script.yaml").write_text(json.dumps(A))
        self.view_module.FOLDER = self.scripts
        self.scripts_yaml = folder / "scripts.yaml"
        self.entities: dict = {}
        self.reload = AsyncMock(side_effect=self.reload_scripts)
        self.hass = SimpleNamespace(
            data={"script": SimpleNamespace(entities=self.entities.values())},
            config=SimpleNamespace(path=lambda name: str(folder / name)),
            services=SimpleNamespace(async_call=self.reload),
            async_add_executor_job=self.executor)
        self.Store.saved = {}

    async def executor(self, function, *args):
        return function(*args)

    async def reload_scripts(self, domain, service, blocking=False):
        data = json.loads(self.scripts_yaml.read_text()) if self.scripts_yaml.exists() else {}
        self.entities.clear()
        for object_id, config in data.items():
            self.entities[object_id] = SimpleNamespace(entity_id="script." + object_id, raw_config=config)
        self.hass.data["script"] = SimpleNamespace(entities=list(self.entities.values()))

    def request(self, body=None, admin=True):
        hass = self.hass

        class Request(dict):
            app = {"hass": hass}  # noqa: RUF012
            content_type = "application/json"
            content_length = 60

            async def json(self):
                return body
        return Request(hass_user=SimpleNamespace(is_admin=admin))

    async def get_rows(self):
        result = await self.view_module.DeclanScriptSyncView().get(self.request())
        return result["payload"]["scripts"]

    async def test_missing_script_is_created_with_confirmation_and_verified(self):
        self.assertEqual((await self.get_rows())[0]["state"], "missing")
        view = self.view_module.DeclanScriptSyncView()
        result = await view.post(self.request({"action": "apply", "file": "good_night.script.yaml"}))
        self.assertEqual(result["payload"]["result"], "applied")
        self.assertIsNone(result["payload"]["backup"])  # there was no scripts.yaml to back up
        self.assertEqual(json.loads(self.scripts_yaml.read_text()), {"declan_good_night": A})
        self.assertEqual((await self.get_rows())[0]["state"], "in_sync")

    async def test_apply_backs_up_and_keeps_other_scripts(self):
        self.scripts_yaml.write_text(json.dumps({"declan_good_night": B, "kitchen": {"alias": "Kitchen"}}))
        await self.reload_scripts("script", "reload")
        rows = await self.get_rows()
        self.assertEqual(rows[0]["state"], "different")
        self.assertIn("light.y", rows[0]["diff"])
        result = await self.view_module.DeclanScriptSyncView().post(
            self.request({"action": "apply", "file": "good_night.script.yaml"}))
        self.assertEqual(result["payload"]["result"], "applied")
        backup = Path(result["payload"]["backup"])
        self.assertEqual(json.loads(backup.read_text())["declan_good_night"], B)
        self.assertEqual(json.loads(self.scripts_yaml.read_text()), {"declan_good_night": A, "kitchen": {"alias": "Kitchen"}})

    async def test_ha_edits_are_detected_and_can_be_kept(self):
        self.scripts_yaml.write_text(json.dumps({"declan_good_night": A}))
        await self.reload_scripts("script", "reload")
        self.assertEqual((await self.get_rows())[0]["state"], "in_sync")  # baseline remembered
        self.entities["declan_good_night"].raw_config = B                  # edited in HA
        row = (await self.get_rows())[0]
        self.assertEqual(row["state"], "ha_changed")
        self.assertIn("light.y", row["ha_yaml"])
        result = await self.view_module.DeclanScriptSyncView().post(
            self.request({"action": "keep_ha", "file": "good_night.script.yaml"}))
        self.assertEqual(result["payload"]["result"], "kept")
        self.assertEqual(self.Store.saved["good_night.script.yaml"]["ha"], sync.fingerprint(B))
        self.reload.assert_not_called()

    async def test_scripts_outside_scripts_yaml_are_never_overwritten(self):
        self.entities["declan_good_night"] = SimpleNamespace(entity_id="script.declan_good_night", raw_config=B)
        result = await self.view_module.DeclanScriptSyncView().post(
            self.request({"action": "apply", "file": "good_night.script.yaml"}))
        self.assertEqual(result["status"], 409)
        self.assertFalse(self.scripts_yaml.exists())

    async def test_requests_are_validated_and_admin_only(self):
        view = self.view_module.DeclanScriptSyncView()
        with self.assertRaises(sys.modules["aiohttp"].web.HTTPForbidden):
            await view.get(self.request(admin=False))
        for body in ({"action": "delete", "file": "good_night.script.yaml"}, {"action": "apply", "file": "../x.yaml"},
                     {"action": "apply"}, [1]):
            with self.subTest(body=body):
                self.assertEqual((await view.post(self.request(body)))["status"], 400)
        self.assertEqual((await view.post(self.request({"action": "apply", "file": "nope.script.yaml"})))["status"], 404)

    def test_panel_and_integration_are_wired(self):
        js = (COMPONENT / "frontend/panel.js").read_text()
        for needle in ("declan_two/script-sync", "loadScriptSync()", "renderScriptSync(", "scriptSyncAction(",
                       "Apply in Home Assistant", "Keep Home Assistant's version"):
            self.assertIn(needle, js)
        self.assertIn("DeclanScriptSyncView()", (COMPONENT / "__init__.py").read_text())


if __name__ == "__main__":
    unittest.main()
