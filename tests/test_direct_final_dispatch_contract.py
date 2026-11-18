"""Contract for direct final dispatch and atomic turn persistence."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SERVER = (ROOT / "server.py").read_text()


class DirectFinalDispatchTests(unittest.TestCase):
    def test_domain_boundaries_used_without_forwarding_wrappers(self):
        ast.parse(SERVER)
        for call in (
            "lighting_result_dispatch.dispatch_lighting_response(",
            "fallback_orchestration.resolve_fallback_result(",
            "response_persona_context.resolve_response_persona(",
            "turn_context_preparation.prepare_turn_context(",
            "turn_response_composition.compose_turn_result(",
            "turn_persistence_dispatch.persist_turn_result(",
        ):
            with self.subTest(call=call):
                self.assertIn(call, SERVER)

    def test_atomic_finalization_order(self):
        lock = SERVER.index("        with SESSION_LOCK:", SERVER.index("fallback_result = "))
        context = SERVER.index("turn_context_preparation.prepare_turn_context(", lock)
        compose = SERVER.index("turn_response_composition.compose_turn_result(", context)
        persist = SERVER.index("turn_persistence_dispatch.persist_turn_result(", compose)
        send = SERVER.index("self.send_json(200, response.to_wire())", persist)
        self.assertLess(lock, context)
        self.assertLess(context, compose)
        self.assertLess(compose, persist)
        self.assertLess(persist, send)

    def test_fallback_exposure_and_action_evidence_still_passed(self):
        self.assertIn("exposed_entities=fallback_entity_authorization.exposed_entities", SERVER)
        self.assertIn("dispatch_fallback=guarded_fallback_dispatch.dispatch_fallback_result", SERVER)
        self.assertIn("action_results=action_results", SERVER)


if __name__ == "__main__":
    unittest.main()
