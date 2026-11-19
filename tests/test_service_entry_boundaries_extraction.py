"""Service entrypoint extraction contracts."""
import unittest
from unittest.mock import Mock, patch

import server
from declan.core import service_entry_boundaries as boundaries


class ServiceEntryBoundaryTests(unittest.TestCase):
    def test_custom_routine_preserves_approval_and_evidence(self):
        r = Mock()
        boundaries.run_custom_routine_result("morning", approved=True, parameters={"a": 1}, r=r)
        kwargs = r.routine_execution_dispatch.run_custom_routine_result.call_args.kwargs
        self.assertTrue(kwargs["approved"])
        self.assertEqual(kwargs["parameters"], {"a": 1})
        self.assertIs(kwargs["parse_steps"], r.routine_action_results_typed)

    def test_media_search_uses_live_configuration(self):
        r = Mock()
        boundaries.search_media_result("song", r=r)
        kwargs = r.media_title_search.search_media_result.call_args.kwargs
        self.assertIs(kwargs["config"], r.configuration)
        self.assertIs(kwargs["connect"], r.ha_device_connection)

    def test_movie_discovery_preserves_inventory_callbacks(self):
        r = Mock()
        boundaries.discover_movie_entities("conn", "lounge", script="script", remote=None, needs_remote=False, r=r)
        kwargs = r.movie_ha_helpers.discover_movie_entities.call_args.kwargs
        self.assertIs(kwargs["inventory_reader"], r.read_ha_inventory_result)
        self.assertIs(kwargs["area_reader"], r.read_ha_areas)

    def test_connection_keeps_redirect_protection(self):
        r = Mock()
        boundaries.ha_device_connection(r=r)
        kwargs = r.ha_speech_transport.ha_device_connection.call_args.kwargs
        self.assertIs(kwargs["redirect_handler"], r.NoRedirect)
        self.assertIs(kwargs["proxy_handler"], r.ProxyHandler)

    def test_conversation_uses_shared_sessions(self):
        r = Mock()
        boundaries.converse("hello", "session", r=r)
        kwargs = r.session_orchestration.converse.call_args.kwargs
        self.assertIs(kwargs["sessions"], r.SESSION_STORE.sessions)
        self.assertIs(kwargs["recall"], r.SESSION_STORE.chat_recall)

    def test_server_media_wrapper_uses_patched_provider(self):
        with patch.object(server.media_title_search, "search_media_result", return_value="ok") as provider:
            self.assertEqual(server.search_media_result("song"), "ok")
            self.assertIs(provider.call_args.kwargs["connect"], server.ha_device_connection)


if __name__ == "__main__":
    unittest.main()
