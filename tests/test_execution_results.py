"""Typed result boundaries, legacy compatibility, and real guarded execution."""
import json
import sqlite3
import tempfile
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from action_executor import ActionResult, execute_verified, summarise, summarise_result
from action_plan import validate_plan
from execution_results import ActionStatus, DispatchResult, ExecutionResult, Outcome
from guarded_fallback import run_guarded_result, run_guarded_fallback
from ha_dispatcher import dispatch_result, dispatch_verified
from test_ha_dispatcher import Opener
import history
import server


class ResultModelTests(TestCase):
    def test_enum_validation_rejects_unknown_and_unverifiable_dispatch_values(self):
        for value in ("success", "complete", "started", "skipped_dependency", None, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                DispatchResult(value)
        with self.assertRaises(ValueError):
            DispatchResult(ActionStatus.CONFIRMED, {"secret": "not a detail"})
        with self.assertRaises(ValueError):
            ActionResult(0, "light.a", "turn_on", "success")
        with self.assertRaises(ValueError):
            ActionResult(0, "light.a", "turn_on", "failed", None)
        for reply, outcome, actions in ((None,"confirmed",()), ("x","success",()),
                                        ("x","confirmed",[]), ("x","confirmed",("bad",))):
            with self.subTest(outcome=outcome), self.assertRaises(ValueError):
                ExecutionResult(reply, outcome, actions)

    def test_legacy_adapters_return_strings_and_json_preserves_exact_values(self):
        step = ActionResult(0, "light.a", "turn_on", "confirmed", "Observed on")
        result = ExecutionResult("Done.", "confirmed", (step,))
        self.assertIs(result.outcome, Outcome.CONFIRMED)
        self.assertIs(step.status, ActionStatus.CONFIRMED)
        self.assertTrue(step.confirmed)
        self.assertEqual(result.as_legacy_pair(), ("Done.", "confirmed"))
        self.assertIs(type(result.as_legacy_pair()[1]), str)
        self.assertIs(type(DispatchResult("confirmed", "on").as_legacy_pair()[0]), str)
        payload = json.loads(json.dumps(result.to_wire()))
        self.assertEqual(payload, {"reply":"Done.", "outcome":"confirmed", "actions":[
            {"index":0,"entity_id":"light.a","service":"turn_on","status":"confirmed","detail":"Observed on"}]})
        self.assertIs(result.as_legacy_mapping()["actions"], result.actions)

    def test_result_objects_and_action_evidence_are_immutable(self):
        step = ActionResult(0, "light.a", "turn_on", ActionStatus.UNVERIFIED)
        result = ExecutionResult("Not confirmed.", Outcome.UNVERIFIED, (step,))
        for target, field, value in ((step,"status",ActionStatus.CONFIRMED),
                                      (result,"outcome",Outcome.CONFIRMED),
                                      (DispatchResult("failed"),"detail","changed")):
            with self.assertRaises(FrozenInstanceError):
                setattr(target, field, value)
        self.assertFalse(step.confirmed)

    def test_dispatcher_adapter_rejects_malformed_values(self):
        expected = DispatchResult("confirmed", "Observed on")
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
            actions = tuple(ActionResult(i,"light.a","turn_on",status) for i,status in enumerate(statuses))
            result = summarise_result(actions)
            self.assertIs(result.outcome, expected)
            self.assertEqual(result.actions, actions)
            self.assertEqual(summarise(actions), result.as_legacy_pair())
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
            return DispatchResult("failed" if action.entity_id == "light.a" else "confirmed")
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

    def test_real_readback_dispatch_and_legacy_pipeline_have_identical_public_results(self):
        action=self.plan[0]
        def args():
            return ("http://ha.local", {}, Opener(["on"]))
        typed=dispatch_result(action,args(),authorised=lambda _:True)
        legacy=dispatch_verified(action,args(),authorised=lambda _:True)
        self.assertIsInstance(typed,DispatchResult)
        self.assertIs(typed.status,ActionStatus.CONFIRMED)
        self.assertEqual(typed.as_legacy_pair(),legacy)
        result=self.pipeline(run_guarded_result,lambda _:typed)
        previous=self.pipeline(run_guarded_fallback,lambda _:legacy)
        self.assertIsInstance(result,ExecutionResult)
        self.assertEqual(result.as_legacy_mapping(),previous)
        self.assertEqual(result.to_wire()["actions"][0]["status"],"confirmed")

    def test_acknowledgement_only_and_clarification_cannot_become_success(self):
        result=self.pipeline(run_guarded_result,lambda _:DispatchResult("unverified","HTTP 200 only"))
        self.assertIs(result.outcome,Outcome.UNVERIFIED)
        self.assertFalse(result.actions[0].confirmed)
        clarified=self.pipeline(run_guarded_result,lambda _:self.fail("Must not dispatch"),plan=())
        self.assertIs(clarified.outcome,Outcome.UNRESOLVED)
        self.assertEqual(clarified.actions,())

    def test_http_fallback_boundary_returns_plain_strings_and_respects_detail_setting(self):
        directory=self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(history,"DATABASE",Path(directory)/"history.db"))
        settings=dict(server.ai_settings.DEFAULTS,enabled=True)
        connection=("http://ha.local",{},Opener(["on","on"]))
        with patch.object(server.ai_settings,"read",return_value=settings), \
             patch.object(server,"ha_device_connection",return_value=connection), \
             patch.object(server,'read_ha_inventory_result',return_value=(self.inventory,None)), \
             patch.object(server,"_bounded_ai_plan",return_value=self.plan), \
             patch.object(server.ai_pricing,"charge",return_value=10):
            for diagnostics in (True,False):
                settings["diagnostics"]=diagnostics
                reply,outcome,steps=server.guarded_openai_fallback(
                    "turn on kitchen",source="assist",exposed_entities=["light.kitchen"])
                self.assertEqual(reply,"All requested actions were confirmed.")
                self.assertEqual(outcome,"confirmed")
                self.assertIs(type(outcome),str)
                self.assertIs(type(steps[0]["status"]),str)
                self.assertEqual(steps[0]["status"],"confirmed")
                self.assertEqual("detail" in steps[0],diagnostics)
                self.assertEqual(json.loads(json.dumps(steps)),steps)
