"""Typed dispatch extraction regression contracts."""
from typing import Any
import unittest
from unittest.mock import Mock, patch

from declan.core import runtime_dispatch_boundaries as boundaries
import server


class RuntimeDispatchBoundaryTests(unittest.TestCase):
    def test_lighting_keeps_live_parser_and_execution_callbacks(self):
        r = Mock()
        evidence: list[dict[str, Any]]
        evidence = []
        boundaries.handle_light_request_result("turn on lounge", action_results=evidence, r=r)
        kwargs = r.lighting_intents.handle_light_request_result.call_args.kwargs
        self.assertIs(kwargs["parse_light_command"], r.parse_light_command)
        self.assertIs(kwargs["set_lights"], r.set_lights_result)
        self.assertIs(kwargs["action_results"], evidence)

    def test_routine_keeps_gate_and_completion_callbacks(self):
        r = Mock()
        boundaries.run_routine_result("morning", approved=True, r=r)
        kwargs = r.routine_execution_dispatch.run_routine_result.call_args.kwargs
        self.assertTrue(kwargs["approved"])
        self.assertIs(kwargs["gates"], r.ROUTINE_EXECUTION_GATES)
        self.assertIs(kwargs["completion"], r.routine_completion_result)

    def test_lighting_dispatch_keeps_switch_and_evidence_callbacks(self):
        r = Mock()
        boundaries.set_lights_result("study", "on", preview=True, r=r)
        kwargs = r.lighting_execution_dispatch.set_lights_result.call_args.kwargs
        self.assertTrue(kwargs["preview"])
        self.assertIs(kwargs["switch_dispatch"], r.set_switch_as_light_result)
        self.assertIs(kwargs["append_evidence"], r.append_action_evidence)

    def test_ai_fallback_keeps_bounded_plan_and_pricing(self):
        r = Mock()
        boundaries.guarded_openai_fallback_result("hello", source="voice", r=r)
        kwargs = r.ai_fallback_dispatch.guarded_openai_fallback_result.call_args.kwargs
        self.assertIs(kwargs["bounded_plan"], r._bounded_ai_plan)
        self.assertIs(kwargs["pricing"], r.ai_pricing.charge)

    def test_server_wrapper_resolves_patched_runtime_dependency(self):
        with patch.object(server.lighting_intents, "handle_light_request_result", return_value="ok") as callback:
            self.assertEqual(server.handle_light_request_result("lights"), "ok")
            self.assertIs(callback.call_args.kwargs["set_lights"], server.set_lights_result)


if __name__ == "__main__":
    unittest.main()
