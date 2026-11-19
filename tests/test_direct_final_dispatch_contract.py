"""Contract for direct final dispatch and atomic turn persistence."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SERVER = (ROOT / "server.py").read_text()
STAGE = (ROOT / "turn_fallback_dispatch.py").read_text()
DISPATCH = (ROOT / "turn_dispatch_orchestration.py").read_text()
PREPARATION = (ROOT / "turn_response_preparation.py").read_text()
FINALIZATION = (ROOT / "turn_atomic_finalization.py").read_text()


class DirectFinalDispatchTests(unittest.TestCase):
    def test_domain_boundaries_used_without_forwarding_wrappers(self):
        ast.parse(SERVER)
        ast.parse(STAGE)
        self.assertIn("lighting_result_dispatch.dispatch_lighting_response(", STAGE)
        self.assertIn("turn_fallback_dispatch.dispatch(", DISPATCH)
        self.assertIn("turn_response_preparation.prepare(", SERVER)
        self.assertIn("fallback_orchestration.resolve_fallback_result(", PREPARATION)
        self.assertIn("response_persona_context.resolve_response_persona(", PREPARATION)
        self.assertIn("turn_atomic_finalization.finalize(", SERVER)
        ast.parse(FINALIZATION)
        for call in (
            "turn_context_preparation.prepare_turn_context(",
            "turn_response_composition.compose_turn_result(",
            "turn_persistence_orchestration.persist_turn_result(",
        ):
            with self.subTest(call=call):
                self.assertIn(call, FINALIZATION)

    def test_atomic_finalization_order(self):
        lock = FINALIZATION.index("with session_lock:")
        context = FINALIZATION.index("turn_context_preparation.prepare_turn_context(", lock)
        compose = FINALIZATION.index("turn_response_composition.compose_turn_result(", context)
        persist = FINALIZATION.index("turn_persistence_orchestration.persist_turn_result(", compose)
        send = SERVER.index("self.send_json(200, response.to_wire())")
        self.assertLess(SERVER.index("turn_atomic_finalization.finalize("), send)
        self.assertLess(lock, context)
        self.assertLess(context, compose)
        self.assertLess(compose, persist)
        self.assertIn("return response", FINALIZATION)
        self.assertIn("response = turn_atomic_finalization.finalize(", SERVER)

    def test_fallback_exposure_and_action_evidence_still_passed(self):
        self.assertIn("exposed_entities=fallback_entity_authorization.exposed_entities", SERVER)
        self.assertIn("dispatch_fallback=guarded_fallback_dispatch.dispatch_fallback_result", SERVER)
        self.assertIn("action_results=action_results", SERVER)


if __name__ == "__main__":
    unittest.main()
