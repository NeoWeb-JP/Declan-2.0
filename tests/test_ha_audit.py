"""Audit regressions using loaded-source fixtures, with no HA actions."""
import asyncio
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components/declan_two"
spec = importlib.util.spec_from_file_location("ha_audit_under_test", INTEGRATION / "ha_audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditTests(unittest.TestCase):
    def report(self, config=None, traces=None, **overrides):
        data = dict(states={"light.ok": {"state": "on"}, "light.offline": {"state": "unavailable"}},
                    registry={"light.disabled": {"disabled": True}}, devices={"device1"}, areas={"kitchen"},
                    services={"light.turn_on", "script.child"},
                    routines=[{"entity_id": "script.example", "state": "off", "config": config}],
                    traces={"script.example": traces or []})
        data.update(overrides)
        before = copy.deepcopy(data)
        result = audit.build_report(**data)
        self.assertEqual(data, before)
        return result

    def codes(self, report):
        return {f["code"] for f in report["routines"][0]["findings"]}

    def test_nested_actions_validate_entities_services_devices_and_areas(self):
        report = self.report({"sequence": [{"choose": [{"conditions": [{"entity_id": "light.missing"}],
                    "sequence": [{"action": "missing.service", "target": {"device_id": "gone", "area_id": "gone"}}]}]}]})
        self.assertTrue({"missing_entity", "missing_service", "missing_device", "missing_area"} <= self.codes(report))
        self.assertEqual(report["summary"]["error"], 4)

    def test_registered_disabled_and_unavailable_entities_are_distinct(self):
        codes = self.codes(self.report({"target": {"entity_id": ["light.disabled", "light.offline"]}}))
        self.assertTrue({"disabled_entity", "unavailable_entity"} <= codes)
        self.assertNotIn("missing_entity", codes)

    def test_templates_are_never_evaluated_or_exposed(self):
        secret = "{{ states('sensor.secret') }}"
        report = self.report({"action": secret, "target": {"entity_id": secret}, "data": {"message": secret}})
        self.assertTrue({"dynamic_service", "dynamic_reference", "template_not_evaluated"} <= self.codes(report))
        self.assertNotIn(secret, str(report))

    def test_disabled_steps_are_not_reported_as_active_dependencies(self):
        report = self.report({"sequence": [{"enabled": False, "action": "bad.service", "entity_id": "bad.entity"}]})
        self.assertEqual(self.codes(report), {"no_trace"})

    def test_missing_config_is_unverified_even_with_entities(self):
        self.assertIn("configuration_unavailable", self.codes(self.report()))

    def test_nested_script_service_requires_entity_and_registered_service(self):
        report = self.report({"sequence": [{"service": "script.child"}]})
        self.assertIn("missing_entity", self.codes(report))
        self.assertNotIn("missing_service", self.codes(report))

    def test_retained_trace_outcomes_are_conservative_and_redacted(self):
        cases = [(dict(state="stopped", script_execution="finished"), "finished_unverified"),
                 (dict(state="stopped", script_execution="failed_conditions"), "skipped"),
                 (dict(state="stopped", script_execution="cancelled"), "cancelled"),
                 (dict(state="running"), "running"), (dict(state="stopped"), "unverified"),
                 (dict(error="token-secret", state="stopped"), "failed")]
        for trace, expected in cases:
            with self.subTest(expected=expected):
                report = self.report({}, [dict(run_id="run1", timestamp={"start": "2026-11-16T10:00:00Z"}, **trace)])
                self.assertEqual(report["routines"][0]["executions"][0]["status"], expected)
                self.assertNotIn("token-secret", str(report))

    def test_only_five_most_recent_runs_and_inventory_without_attributes(self):
        report = self.report({}, [{"run_id": str(i), "timestamp": {"start": str(i)}} for i in range(7)])
        self.assertEqual([r["run_id"] for r in report["routines"][0]["executions"]], ["6", "5", "4", "3", "2"])
        self.assertEqual(report["summary"]["entities"], 3)
        self.assertNotIn("attributes", str(report))

    def test_missing_sources_are_explicit(self):
        report = self.report({}, gaps=["script: retained traces unavailable"])
        self.assertEqual(report["coverage"], "partial")
        self.assertTrue(report["read_only"])
        self.assertIn("no_trace", self.codes(report))


class AuditViewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Lightweight interface doubles; import the real collector and handler.
        self.web = SimpleNamespace(HTTPForbidden=type("Forbidden", (Exception,), {}),
                                   json_response=lambda report, **kwargs: (report, kwargs))
        self.reg = SimpleNamespace(entities={"automation.disabled": SimpleNamespace(disabled_by="user")})
        self.devices = SimpleNamespace(devices={"device1": object()})
        self.areas = SimpleNamespace(areas={"kitchen": object()})
        def module(name, **values):
            return types.SimpleNamespace(**values)
        self.trace_rows = []
        async def trace_list(*args):
            return self.trace_rows
        modules = {"aiohttp": module("aiohttp", web=self.web),
                   "homeassistant": module("homeassistant"),
                   "homeassistant.components": module("components"),
                   "homeassistant.components.http": module("http", HomeAssistantView=object),
                   "homeassistant.components.trace.util": module("trace", async_list_traces=trace_list),
                   "homeassistant.helpers": module("helpers",
                       area_registry=SimpleNamespace(async_get=lambda hass: self.areas),
                       device_registry=SimpleNamespace(async_get=lambda hass: self.devices),
                       entity_registry=SimpleNamespace(async_get=lambda hass: self.reg)),
                   "audit_fixture": module("audit_fixture"), "audit_fixture.ha_audit": audit}
        self.patch = patch.dict(sys.modules, modules)
        self.patch.start()
        spec = importlib.util.spec_from_file_location("audit_fixture.ha_audit_view", INTEGRATION / "ha_audit_view.py")
        self.view = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.view)
        entity = SimpleNamespace(entity_id="automation.actual_entity", raw_config={"id": "persistent-id", "actions": []},
                                 action_script=SimpleNamespace(sequence=[{"action": "light.turn_on", "entity_id": "light.missing"}]),
                                 referenced_entities={"light.missing"})
        state = SimpleNamespace(entity_id=entity.entity_id, state="on", attributes={"friendly_name": "Packaged automation", "secret": "hidden"})
        self.hass = SimpleNamespace(data={"automation": SimpleNamespace(entities=[entity])},
                                    states=SimpleNamespace(async_all=lambda: [state]),
                                    services=SimpleNamespace(async_services=lambda: {"light": {"turn_on": object()}}))

    def tearDown(self):
        self.patch.stop()

    async def test_collector_uses_loaded_sources_and_persistent_trace_id(self):
        self.trace_rows.append({"item_id": "persistent-id", "run_id": "run1", "script_execution": "finished"})
        report = await self.view.collect_report(self.hass)
        row = next(r for r in report["routines"] if r["entity_id"] == "automation.actual_entity")
        self.assertEqual(row["executions"][0]["run_id"], "run1")
        self.assertIn("missing_entity", {f["code"] for f in row["findings"]})
        disabled = next(r for r in report["routines"] if r["entity_id"] == "automation.disabled")
        self.assertTrue(disabled["disabled"])
        self.assertNotIn("hidden", str(report))

    async def test_non_admin_cannot_collect(self):
        request = {"hass_user": SimpleNamespace(is_admin=False)}
        with self.assertRaises(self.web.HTTPForbidden):
            await self.view.DeclanHAAuditView().get(request)
        self.assertTrue(self.view.DeclanHAAuditView.requires_auth)
        self.assertFalse(hasattr(self.view.DeclanHAAuditView, "post"))

    async def test_admin_get_is_fresh_and_no_store(self):
        class Request(dict):
            app = {"hass": self.hass}
        request = Request(hass_user=SimpleNamespace(is_admin=True))
        report, options = await self.view.DeclanHAAuditView().get(request)
        self.assertTrue(report["read_only"])
        self.assertEqual(options["headers"]["Cache-Control"], "no-store")


if __name__ == "__main__":
    unittest.main()
