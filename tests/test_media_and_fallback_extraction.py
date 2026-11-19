"""Regression checks for media search and permission-bounded AI extraction."""
import unittest
from unittest.mock import patch

import server
from declan.music import media_title_search
from declan.ai import ai_fallback_dispatch
from execution_results import Outcome


class MediaAndFallbackExtractionTests(unittest.TestCase):
    def test_media_wrapper_keeps_runtime_patch_points(self):
        with patch.object(media_title_search, "search_media_result", return_value="sentinel") as extracted:
            self.assertEqual(server.search_media_result("where can i watch dune"), "sentinel")
        kwargs = extracted.call_args.kwargs
        self.assertIs(kwargs["config"], server.configuration)
        self.assertIs(kwargs["connect"], server.ha_device_connection)
        self.assertIs(kwargs["agents"], server.media_search_agents)
        self.assertIs(kwargs["request_factory"], server.Request)

    def test_media_search_does_not_match_unrelated_commands(self):
        self.assertIsNone(server.search_media_result("turn on kitchen lights"))

    def test_media_search_rejects_mixed_device_commands(self):
        result = server.search_media_result("where can i watch dune and then unlock door")
        self.assertEqual(result.outcome, Outcome.UNRESOLVED)

    def test_fallback_wrapper_keeps_runtime_patch_points(self):
        with patch.object(ai_fallback_dispatch, "guarded_openai_fallback_result", return_value="sentinel") as extracted:
            self.assertEqual(server.guarded_openai_fallback_result("test", source="voice"), "sentinel")
        kwargs = extracted.call_args.kwargs
        self.assertIs(kwargs["connect"], server.ha_device_connection)
        self.assertIs(kwargs["inventory_reader"], server.read_ha_inventory_result)
        self.assertIs(kwargs["bounded_plan"], server._bounded_ai_plan)
        self.assertIs(kwargs["dispatcher"], server.ha_dispatcher.dispatch_result)
        self.assertIs(kwargs["evidence_factory"], server.FallbackActionEvidence)
        self.assertIs(kwargs["response_factory"], server.guarded_fallback_dispatch.FallbackResponse)

    def test_disabled_fallback_does_not_contact_ha(self):
        with patch.object(server.ai_settings, "read", return_value={"enabled": False}):
            with patch.object(server, "ha_device_connection", side_effect=AssertionError("HA must not be contacted")):
                self.assertIsNone(server.guarded_openai_fallback_result("turn on light", source="voice"))


if __name__ == "__main__":
    unittest.main()
