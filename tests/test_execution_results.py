"""Typed result boundaries, legacy compatibility, and real guarded execution."""
from result_pairs import pair
from typing import Any, cast
import json
import sqlite3
import tempfile
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from declan.ai.action_executor import ActionResult, execute_verified, summarise_result
from declan.ai.action_plan import validate_plan
from declan.core.execution_results import ActionStatus, DispatchResult, ExecutionResult, Outcome
from declan.ai.guarded_fallback import run_guarded_result
from declan.ha.ha_dispatcher import dispatch_result
from test_ha_dispatcher import Opener
from declan.core import history
import server


class ResultModelTests(TestCase):
    def test_enum_validation_rejects_unknown_and_unverifiable_dispatch_values(self):
        for value in ("success", "complete", "started", "skipped_dependency", None, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                cast(Any, DispatchResult)(value)
        with self.assertRaises(ValueError):
            cast(Any, DispatchResult)(ActionStatus.CONFIRMED, {"secret": "not a detail"})
        with self.assertRaises(ValueError):
            cast(Any, ActionResult)(0, "light.a", "turn_on", "success")
        with self.assertRaises(ValueError):
            cast(Any, ActionResult)(0, "light.a", "turn_on", ActionStatus.FAILED, None)
        for reply, outcome, actions in ((None,"confirmed",()), ("x","success",()),
                                        ("x","confirmed",[]), ("x","confirmed",("bad",))):
            with self.subTest(outcome=outcome), self.assertRaises(ValueError):
                cast(Any, ExecutionResult)(reply, outcome, actions)

    def test_legacy_adapters_return_strings_and_json_preserves_exact_values(self):
        step = ActionResult(0, "light.a", "turn_on", ActionStatus.CONFIRMED, "Observed on")
        result = ExecutionResult("Done.", Outcome.CONFIRMED, (step,))
        self.assertIs(result.outcome, Outcome.CONFIRMED)
        self.assertIs(step.status, ActionStatus.CONFIRMED)
        self.assertTrue(step.confirmed)
        self.assertEqual(pair(result), ("Done.", "confirmed"))
        self.assertIs(type(pair(result)[1]), str)
        self.assertIs(type(pair(DispatchResult(ActionStatus.CONFIRMED, "on"))[0]), str)
        payload = json.loads(json.dumps(result.to_wire()))
        self.assertEqual(payload, {"reply":"Done.", "outcome":"confirmed", "actions":[
            {"index":0,"entity_id":"light.a","service":"turn_on","status":"confirmed","detail":"Observed on"}]})

    def test_result_objects_and_action_evidence_are_immutable(self):
        step = ActionResult(0, "light.a", "turn_on", ActionStatus.UNVERIFIED)
        result = ExecutionResult("Not confirmed.", Outcome.UNVERIFIED, (step,))
        for target, field, value in ((step,"status",ActionStatus.CONFIRMED),
                                      (result,"outcome",Outcome.CONFIRMED),
                                      (DispatchResult(ActionStatus.FAILED),"detail","changed")):
            with self.assertRaises(FrozenInstanceError):
                setattr(target, field, value)
        self.assertFalse(step.confirmed)

    def test_dispatcher_adapter_rejects_malformed_values(self):
        expected = DispatchResult(ActionStatus.CONFIRMED, "Observed on")
        self.assertIs(DispatchResult.coerce(expected), expected)
        self.assertEqual(DispatchResult.coerce(("confirmed", "Observed on")), expected)
        self.assertEqual(DispatchResult.coerce(["confirmed", "Observed on"]), expected)
        for value in (None, "confirmed", {"status":"confirmed"}, ("confirmed",), ("confirmed","on",1)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                DispatchResult.coerce(value)

    def test_summaries_keep_partial_unverified_and_empty_results_distinct(self):
        for statuses, expected in (
            ((), Outcome.UNRESOLVED), (("confirmed",), Outcome.CONFIRMED),
            (("confirmed","failed","skipped_dependency"), Outcome.PARTIAL),
            (("unverified",), Outcome.UNVERIFIED), (("failed",), Outcome.UNVERIFIED),
        ):
            actions = tuple(ActionResult(i,"light.a","turn_on",ActionStatus(status)) for i,status in enumerate(statuses))
            result = summarise_result(actions)
            self.assertIs(result.outcome, expected)
            self.assertEqual(result.actions, actions)
        with self.assertRaises(ValueError):
            summarise_result(("not action evidence",))

    def test_typed_failed_dispatch_skips_only_its_dependencies(self):
        plan = validate_plan({"actions":[
            {"entity_id":"light.a","service":"turn_on"},
            {"entity_id":"light.b","service":"turn_on"},
            {"entity_id":"light.c","service":"turn_off","depends_on":[0]},
        ]}, {"light.a","light.b","light.c"})
        calls=[]
        def dispatch(action):
            calls.append(action.entity_id)
            return DispatchResult(ActionStatus.FAILED if action.entity_id == "light.a" else ActionStatus.CONFIRMED)
        actions=execute_verified(plan,dispatch)
        self.assertEqual(calls,["light.a","light.b"])
        self.assertEqual([row.status for row in actions],
                         [ActionStatus.FAILED, ActionStatus.CONFIRMED, ActionStatus.SKIPPED_DEPENDENCY])
        self.assertIs(summarise_result(actions).outcome, Outcome.PARTIAL)
        for bad in (("started","accepted"), ("confirmed",None), None):
            row=execute_verified(plan[:1],lambda _:bad)[0]
            self.assertIs(row.status,ActionStatus.FAILED)
            self.assertEqual(row.detail,"Dispatch or verification failed")


class TypedPipelineTests(TestCase):
    def setUp(self):
        self.plan=validate_plan({"actions":[{"entity_id":"light.kitchen","service":"turn_on"}]},
                                {"light.kitchen"})
        self.inventory=[{"entity_id":"light.kitchen","state":"off","attributes":{}}]

    def pipeline(self, function, dispatch, *, plan=None):
        with sqlite3.connect(":memory:") as db:
            return function("turn kitchen on",self.inventory,planner=lambda *_:self.plan if plan is None else plan,
                            dispatcher=dispatch,budget_db=db,monthly_limit_micro_usd=100,
                            request_ceiling_micro_usd=30,charge_micro_usd=lambda:10)

    def test_real_readback_dispatch_flows_through_the_typed_pipeline(self):
        action=self.plan[0]
        typed=dispatch_result(action,("http://ha.local", {}, Opener(["on"])),authorised=lambda _:True)
        self.assertIsInstance(typed,DispatchResult)
        self.assertIs(typed.status,ActionStatus.CONFIRMED)
        result=self.pipeline(run_guarded_result,lambda _:typed)
        self.assertIsInstance(result,ExecutionResult)
        self.assertIs(result.outcome,Outcome.CONFIRMED)
        self.assertEqual(result.to_wire()["actions"][0]["status"],"confirmed")

    def test_acknowledgement_only_and_clarification_cannot_become_success(self):
        result=self.pipeline(run_guarded_result,lambda _:DispatchResult(ActionStatus.UNVERIFIED,"HTTP 200 only"))
        self.assertIs(result.outcome,Outcome.UNVERIFIED)
        self.assertFalse(result.actions[0].confirmed)
        clarified=self.pipeline(run_guarded_result,lambda _:self.fail("Must not dispatch"),plan=())
        self.assertIs(clarified.outcome,Outcome.UNRESOLVED)
        self.assertEqual(clarified.actions,())

    def test_http_fallback_boundary_returns_plain_strings_and_respects_detail_setting(self):
        directory=self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(history,"DATABASE",Path(directory)/"history.db"))
        settings=dict(server.ai_settings.DEFAULTS,enabled=True)
        connection: tuple[Any, ...]
        connection=("http://ha.local",{},Opener(["on","on"]))
        with patch.object(server.ai_settings,"read",return_value=settings), \
             patch.object(server,"ha_device_connection",return_value=connection), \
             patch.object(server,'read_ha_inventory_result',return_value=(self.inventory,None)), \
             patch.object(server,"_bounded_ai_plan",return_value=self.plan), \
             patch.object(server.ai_pricing,"charge",return_value=10):
            for diagnostics in (True,False):
                settings["diagnostics"]=diagnostics
                reply,outcome,steps=pair(server.guarded_openai_fallback_result(
                    "turn on kitchen",source="assist",exposed_entities=["light.kitchen"]))
                self.assertEqual(reply,"All requested actions were confirmed.")
                self.assertEqual(outcome,"confirmed")
                self.assertIs(type(outcome),str)
                self.assertIs(type(steps[0]["status"]),str)
                self.assertEqual(steps[0]["status"],"confirmed")
                self.assertEqual("detail" in steps[0],diagnostics)
                self.assertEqual(json.loads(json.dumps(steps)),steps)
