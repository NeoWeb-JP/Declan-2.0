"""Audit regressions using loaded-source fixtures, with no HA actions."""
import asyncio
import copy
import json
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
review_spec = importlib.util.spec_from_file_location("audit_reviews_under_test", INTEGRATION / "audit_reviews.py")
reviews = importlib.util.module_from_spec(review_spec)
review_spec.loader.exec_module(reviews)


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

    def test_stale_registry_records_are_distinct_from_loaded_routines_and_counts(self):
        report = self.report(routines=[{"entity_id": "script.current", "config": {}, "stale": False},
                                       {"entity_id": "script.old", "config": None, "stale": True}],
                             states={"script.current": {"state": "unavailable"}, "script.old": {"state": "unavailable"}})
        self.assertEqual(report["summary"]["scripts"], 1)
        self.assertEqual(report["summary"]["stale"], 1)
        self.assertFalse(report["routines"][0]["stale"])
        self.assertTrue(next(row for row in report["entities"] if row["entity_id"] == "script.old")["stale"])

    def test_continue_on_error_is_partial_and_step_values_are_redacted(self):
        steps = audit.trace_steps({"trace": {"sequence/0": [{"error": "secret-token", "changed_variables": {"secret": "hidden"}}],
                                             "sequence/1": [{"result": {"success": True}}]}})
        report = self.report({}, [{"script_execution": "finished", "audit_steps": steps}])
        execution = report["routines"][0]["executions"][0]
        self.assertEqual(execution["status"], "partial")
        self.assertEqual(execution["steps"][0], {"path": "sequence/0", "status": "failed"})
        self.assertIn("execution_failed", self.codes(report))
        self.assertNotIn("secret-token", str(report))
        self.assertNotIn("hidden", str(report))

    def test_review_fingerprint_ignores_normal_runs_but_changes_for_source_and_new_failures(self):
        baseline = self.report({"sequence": []})["routines"][0]["fingerprint"]
        finished = self.report({"sequence": []}, [{"run_id": "ok", "script_execution": "finished"}])["routines"][0]["fingerprint"]
        self.assertEqual(baseline, finished)
        modified = self.report({"sequence": [{"delay": 1}]})["routines"][0]["fingerprint"]
        failed = self.report({"sequence": []}, [{"run_id": "bad", "error": "hidden"}])["routines"][0]["fingerprint"]
        failed_again = self.report({"sequence": []}, [{"run_id": "bad2", "error": "hidden"}])["routines"][0]["fingerprint"]
        self.assertNotEqual(baseline, modified)
        self.assertNotEqual(baseline, failed)
        self.assertNotEqual(failed, failed_again)


class AuditViewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Lightweight interface doubles; import the real collector and handler.
        self.web = SimpleNamespace(HTTPForbidden=type("Forbidden", (Exception,), {}),
                                   HTTPBadRequest=type("BadRequest", (Exception,), {}),
                                   json_response=lambda report, **kwargs: (report, kwargs))
        saved_reviews = {}
        class FakeStore:
            def __init__(self, *args): pass
            async def async_load(self): return dict(saved_reviews)
            async def async_save(self, records):
                saved_reviews.clear()
                saved_reviews.update(records)
        self.reg = SimpleNamespace(entities={"automation.disabled": SimpleNamespace(disabled_by="user")})
        # HA 2026.11 devices is a collection of entries, not an ID-keyed map.
        # SimpleNamespace is deliberately unhashable, like HA DeviceEntry.
        self.devices = SimpleNamespace(devices=[SimpleNamespace(id="device1")])
        self.areas = SimpleNamespace(async_list_areas=lambda: [SimpleNamespace(id="kitchen")])
        def module(name, **values):
            return types.SimpleNamespace(**values)
        self.trace_rows = []
        self.trace_details = {"context": {"id": "context1"}, "trace": {"action/0": [{"error": "secret-token"}]}}
        async def trace_list(*args):
            return self.trace_rows
        async def trace_get(*args):
            return self.trace_details
        modules = {"aiohttp": module("aiohttp", web=self.web),
                   "homeassistant": module("homeassistant"),
                   "homeassistant.components": module("components"),
                   "homeassistant.components.http": module("http", HomeAssistantView=object),
                   "homeassistant.components.trace.util": module("trace", async_list_traces=trace_list, async_get_trace=trace_get),
                   "homeassistant.helpers.storage": module("storage", Store=FakeStore),
                   "homeassistant.util": module("util"),
                   "homeassistant.util.yaml": module("yaml", dump=lambda config: json.dumps(config)),
                   "homeassistant.helpers": module("helpers",
                       area_registry=SimpleNamespace(async_get=lambda hass: self.areas),
                       device_registry=SimpleNamespace(async_get=lambda hass: self.devices),
                       entity_registry=SimpleNamespace(async_get=lambda hass: self.reg)),
                   "audit_fixture": module("audit_fixture"), "audit_fixture.ha_audit": audit,
                   "audit_fixture.audit_reviews": reviews}
        self.patch = patch.dict(sys.modules, modules)
        self.patch.start()
        spec = importlib.util.spec_from_file_location("audit_fixture.ha_audit_view", INTEGRATION / "ha_audit_view.py")
        self.view = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.view)
        result_spec = importlib.util.spec_from_file_location("audit_fixture.script_result_view", INTEGRATION / "script_result_view.py")
        self.result_view = importlib.util.module_from_spec(result_spec)
        result_spec.loader.exec_module(self.result_view)
        entity = SimpleNamespace(entity_id="automation.actual_entity", raw_config={"id": "persistent-id", "actions": []},
                                 action_script=SimpleNamespace(sequence=[{"action": "light.turn_on", "entity_id": "light.missing"}]),
                                 referenced_entities={"light.missing"})
        state = SimpleNamespace(entity_id=entity.entity_id, state="on", attributes={"friendly_name": "Packaged automation", "secret": "hidden"})
        async def executor(function, *args): return function(*args)
        self.hass = SimpleNamespace(data={"automation": SimpleNamespace(entities=[entity], get_entity=lambda entity_id: entity if entity_id == entity.entity_id else None)},
                                    async_add_executor_job=executor,
                                    states=SimpleNamespace(async_all=lambda: [state]),
                                    services=SimpleNamespace(async_services=lambda: {"light": {"turn_on": object()}}))

    def tearDown(self):
        self.patch.stop()

    async def test_collector_uses_loaded_sources_and_persistent_trace_id(self):
        self.trace_rows.append({"item_id": "persistent-id", "run_id": "run1", "script_execution": "finished"})
        report = await self.view.collect_report(self.hass)
        row = next(r for r in report["routines"] if r["entity_id"] == "automation.actual_entity")
        self.assertEqual(row["executions"][0]["run_id"], "run1")
        self.assertEqual(row["executions"][0]["status"], "partial")
        self.assertIn("missing_entity", {f["code"] for f in row["findings"]})
        disabled = next(r for r in report["routines"] if r["entity_id"] == "automation.disabled")
        self.assertTrue(disabled["disabled"])
        self.assertNotIn("hidden", str(report))
        self.assertTrue(row["yaml_available"])
        self.assertFalse(disabled["yaml_available"])
        self.assertTrue(disabled["stale"])
        self.assertFalse(row["stale"])

    def yaml_request(self, entity_id, admin=True):
        class Request(dict):
            app = {"hass": self.hass}
            query = {"entity_id": entity_id}
        return Request(hass_user=SimpleNamespace(is_admin=admin))

    async def test_yaml_export_reads_current_loaded_definition_without_runtime_metadata(self):
        entity = self.hass.data["automation"].entities[0]
        entity.raw_config["alias"] = "Current edited automation"
        entity.raw_config["variables"] = {"message": "{{ states('sensor.example') }}"}
        payload, options = await self.view.DeclanAuditYamlView().get(self.yaml_request(entity.entity_id))
        self.assertEqual(payload["filename"], entity.entity_id + ".yaml")
        self.assertIn("Current edited automation", payload["yaml"])
        self.assertIn("{{ states('sensor.example') }}", payload["yaml"])
        self.assertNotIn("loaded_sequence", payload["yaml"])
        self.assertNotIn("reviewed_at", payload["yaml"])
        self.assertEqual(options["headers"]["Cache-Control"], "no-store")

    async def test_yaml_export_rejects_non_admin_invalid_ids_and_stale_entities(self):
        with self.assertRaises(self.web.HTTPForbidden):
            await self.view.DeclanAuditYamlView().get(self.yaml_request("automation.actual_entity", admin=False))
        with self.assertRaises(self.web.HTTPBadRequest):
            await self.view.DeclanAuditYamlView().get(self.yaml_request("../../secrets.yaml"))
        payload, options = await self.view.DeclanAuditYamlView().get(self.yaml_request("automation.disabled"))
        self.assertEqual(options["status"], 404)
        self.assertNotIn("yaml", payload)

    async def test_yaml_export_failure_is_redacted(self):
        async def fail(*args): raise ValueError("private-configuration-value")
        with patch.object(self.hass, "async_add_executor_job", fail), self.assertLogs(self.view._LOGGER, level="ERROR") as logs:
            payload, options = await self.view.DeclanAuditYamlView().get(self.yaml_request("automation.actual_entity"))
        self.assertEqual(options["status"], 503)
        self.assertNotIn("private-configuration-value", str(payload) + str(logs.output))

    async def test_current_entry_collection_and_legacy_mapping_validate_same_device(self):
        self.hass.data["automation"].entities[0].action_script.sequence = [
            {"action": "light.turn_on", "target": {"device_id": "device1", "area_id": "kitchen"}}]
        for entries in ([SimpleNamespace(id="device1")], {"device1": SimpleNamespace(id="device1")}):
            self.devices.devices = entries
            report = await self.view.collect_report(self.hass)
            routine = next(row for row in report["routines"] if row["entity_id"] == "automation.actual_entity")
            self.assertNotIn("missing_device", {f["code"] for f in routine["findings"]})
            self.assertNotIn("missing_area", {f["code"] for f in routine["findings"]})

    async def test_collection_failure_returns_redacted_503(self):
        class Request(dict):
            app = {"hass": self.hass}
        request = Request(hass_user=SimpleNamespace(is_admin=True))
        async def fail(*args):
            raise TypeError("private-token-must-not-appear")
        with patch.object(self.view, "collect_report", fail), self.assertLogs(self.view._LOGGER, level="ERROR") as logs:
            report, options = await self.view.DeclanHAAuditView().get(request)
        self.assertEqual(options["status"], 503)
        self.assertEqual(report, {"error": "audit_collection_failed"})
        self.assertNotIn("private-token", str(report) + str(logs.output))
        self.assertIn("TypeError", str(logs.output))

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

    def review_request(self, body, admin=True):
        class Request(dict):
            app = {"hass": self.hass}
            async def json(self): return body
        return Request(hass_user=SimpleNamespace(is_admin=admin))

    async def test_review_persists_and_source_changes_reopen_it(self):
        report = await self.view.collect_report(self.hass)
        row = next(row for row in report["routines"] if row["entity_id"] == "automation.actual_entity")
        body = {"entity_id": row["entity_id"], "fingerprint": row["fingerprint"], "reviewed": True}
        saved, _ = await self.view.DeclanAuditReviewView().post(self.review_request(body))
        self.assertTrue(saved["reviewed"])
        self.hass.data.pop("declan_two_audit_reviews")  # Reload from persistent Store.
        await reviews.apply_reviews(self.hass, report)
        self.assertTrue(row["reviewed"])
        self.hass.data["automation"].entities[0].raw_config["description"] = "Changed"
        changed = await self.view.collect_report(self.hass)
        await reviews.apply_reviews(self.hass, changed)
        self.assertFalse(next(row for row in changed["routines"] if row["entity_id"] == body["entity_id"])["reviewed"])
        rejected, options = await self.view.DeclanAuditReviewView().post(self.review_request(body))
        self.assertEqual(options["status"], 409)
        self.assertEqual(rejected["error"], "routine_changed")

    async def test_review_can_be_undone_and_needs_admin(self):
        report = await self.view.collect_report(self.hass)
        row = report["routines"][0]
        body = {"entity_id": row["entity_id"], "fingerprint": row["fingerprint"], "reviewed": True}
        with self.assertRaises(self.web.HTTPForbidden):
            await self.view.DeclanAuditReviewView().post(self.review_request(body, admin=False))
        await self.view.DeclanAuditReviewView().post(self.review_request(body))
        body["reviewed"] = False
        await self.view.DeclanAuditReviewView().post(self.review_request(body))
        await reviews.apply_reviews(self.hass, report)
        self.assertFalse(row["reviewed"])

    async def test_review_save_failure_preserves_previous_status(self):
        report = await self.view.collect_report(self.hass)
        row = report["routines"][0]
        body = {"entity_id": row["entity_id"], "fingerprint": row["fingerprint"], "reviewed": True}
        state = await reviews.review_state(self.hass)
        async def fail(*args): raise OSError("disk unavailable")
        with patch.object(state["store"], "async_save", fail):
            _, options = await self.view.DeclanAuditReviewView().post(self.review_request(body))
        self.assertEqual(options["status"], 503)
        self.assertEqual(state["records"], {})

    async def test_exact_script_context_completion_not_an_unrelated_run(self):
        self.hass.data["script"] = SimpleNamespace(get_entity=lambda entity_id: SimpleNamespace(unique_id="actual_script_id"))
        self.trace_rows.append({"run_id": "run1", "script_execution": "finished"})
        self.trace_details["trace"] = {"sequence/0": [{"result": {"data": "secret"}}]}
        result = await self.result_view.lookup_result(self.hass, "script.dinner", "context1")
        self.assertEqual(result["status"], "finished_unverified")
        self.assertEqual(result["run_id"], "run1")
        self.assertNotIn("secret", str(result))
        unrelated = await self.result_view.lookup_result(self.hass, "script.dinner", "context2")
        self.assertEqual(unrelated["status"], "unverified")
        self.trace_rows.append({"run_id": "run2", "script_execution": "finished"})
        ambiguous = await self.result_view.lookup_result(self.hass, "script.dinner", "context1")
        self.assertEqual(ambiguous["status"], "unverified")


if __name__ == "__main__":
    unittest.main()
