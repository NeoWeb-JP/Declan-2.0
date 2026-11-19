"""Server-level wiring for runtime dispatch and service-entry boundaries."""
from typing import Any
import unittest
from unittest.mock import patch

import server


class ServerDispatchWiringTests(unittest.TestCase):
    def test_lighting_keeps_live_parser_and_execution_callbacks(self):
        evidence: list[dict[str, Any]]
        evidence = []
        with patch.object(server.lighting_intents, "handle_light_request_result") as handle:
            server.handle_light_request_result("turn on lounge", action_results=evidence)
        kwargs = handle.call_args.kwargs
        self.assertIs(kwargs["parse_light_command"], server.parse_light_command)
        self.assertIs(kwargs["set_lights"], server.set_lights_result)
        self.assertIs(kwargs["action_results"], evidence)

    def test_routine_keeps_gate_and_completion_callbacks(self):
        with patch.object(server.routine_execution_dispatch, "run_routine_result") as run:
            server.run_routine_result("morning", approved=True)
        kwargs = run.call_args.kwargs
        self.assertTrue(kwargs["approved"])
        self.assertIs(kwargs["gates"], server.ROUTINE_EXECUTION_GATES)
        self.assertIs(kwargs["completion"], server.routine_completion_result)

    def test_lighting_dispatch_keeps_switch_and_evidence_callbacks(self):
        with patch.object(server.lighting_execution_dispatch, "set_lights_result") as dispatch:
            server.set_lights_result("study", "on", preview=True)
        kwargs = dispatch.call_args.kwargs
        self.assertTrue(kwargs["preview"])
        self.assertIs(kwargs["switch_dispatch"], server.set_switch_as_light_result)
        self.assertIs(kwargs["append_evidence"], server.append_action_evidence)

    def test_ai_fallback_keeps_bounded_plan_and_pricing(self):
        with patch.object(server.ai_fallback_dispatch, "guarded_openai_fallback_result") as fallback:
            server.guarded_openai_fallback_result("hello", source="voice")
        kwargs = fallback.call_args.kwargs
        self.assertIs(kwargs["bounded_plan"], server._bounded_ai_plan)
        self.assertIs(kwargs["pricing"], server.ai_pricing.charge)

    def test_custom_routine_preserves_approval_and_evidence(self):
        with patch.object(server.routine_execution_dispatch, "run_custom_routine_result") as run:
            server.run_custom_routine_result("morning", approved=True, parameters={"a": 1})
        kwargs = run.call_args.kwargs
        self.assertTrue(kwargs["approved"])
        self.assertEqual(kwargs["parameters"], {"a": 1})
        self.assertIs(kwargs["parse_steps"], server.routine_action_results_typed)

    def test_media_search_uses_live_configuration(self):
        with patch.object(server.media_title_search, "search_media_result", return_value="ok") as provider:
            self.assertEqual(server.search_media_result("song"), "ok")
        self.assertIs(provider.call_args.kwargs["config"], server.configuration)
        self.assertIs(provider.call_args.kwargs["connect"], server.ha_device_connection)

    def test_movie_discovery_preserves_inventory_callbacks(self):
        with patch.object(server.movie_ha_helpers, "discover_movie_entities") as discover:
            server.discover_movie_entities("conn", "lounge", script="script", remote=None, needs_remote=False)
        kwargs = discover.call_args.kwargs
        self.assertIs(kwargs["inventory_reader"], server.read_ha_inventory_result)
        self.assertIs(kwargs["area_reader"], server.read_ha_areas)

    def test_connection_keeps_redirect_protection(self):
        with patch.object(server.ha_speech_transport, "ha_device_connection") as connect:
            server.ha_device_connection()
        kwargs = connect.call_args.kwargs
        self.assertIs(kwargs["redirect_handler"], server.NoRedirect)
        self.assertIs(kwargs["proxy_handler"], server.ProxyHandler)

    def test_conversation_uses_shared_sessions(self):
        with patch.object(server.session_orchestration, "converse") as converse:
            server.converse("hello", "session")
        kwargs = converse.call_args.kwargs
        self.assertIs(kwargs["sessions"], server.SESSION_STORE.sessions)
        self.assertIs(kwargs["recall"], server.SESSION_STORE.chat_recall)


if __name__ == "__main__":
    unittest.main()
