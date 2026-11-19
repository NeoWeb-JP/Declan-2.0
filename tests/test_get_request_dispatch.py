"""Regression tests for extracted GET request routing and access gate."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import get_request_dispatch


class FakeHandler:
    def __init__(self, path):
        self.path = path
        self.responses = []

    def send_json(self, status, body):
        self.responses.append((status, body))


def invoke(handler):
    return get_request_dispatch.dispatch(
        handler, assist_token="secret", ingress=False, logo_path="logo.png",
        health_readiness=None, ha_status=None, release_version="test",
        music=None, configuration=None, script_discovery=None,
        ha_connection=None, command_responses=None, history=None,
        logs=None, diagnostics=None, updates=None, voicepipeline=None,
        voice_profiles=None, ai_budget=None, ai_settings=None,
        ai_credentials=None, spotify_playlists=None,
    )


class GetRequestDispatchTests(unittest.TestCase):
    def test_denied_access_never_dispatches(self):
        handler = FakeHandler("/health")
        with patch.object(get_request_dispatch.get_access_gate_http, "enforce_access", return_value=False):
            with patch.object(get_request_dispatch.system_read_routes, "dispatch") as route:
                invoke(handler)
        route.assert_not_called()
        self.assertEqual(handler.responses, [])

    def test_system_route_is_dispatched_after_access(self):
        handler = FakeHandler("/health")
        with patch.object(get_request_dispatch.get_access_gate_http, "enforce_access", return_value=True):
            with patch.object(get_request_dispatch.system_read_routes, "handles", return_value=True):
                with patch.object(get_request_dispatch.system_read_routes, "dispatch") as route:
                    invoke(handler)
        route.assert_called_once()
        self.assertIs(route.call_args.args[0], handler)

    def test_unknown_route_returns_404(self):
        handler = FakeHandler("/not-a-real-route")
        with patch.object(get_request_dispatch.get_access_gate_http, "enforce_access", return_value=True):
            for module in (
                get_request_dispatch.system_read_routes,
                get_request_dispatch.native_read_routes,
                get_request_dispatch.operational_read_routes,
                get_request_dispatch.settings_read_routes,
                get_request_dispatch.history_read_routes,
            ):
                self.addCleanup(patch.stopall)
            with patch.object(get_request_dispatch.system_read_routes, "handles", return_value=False), \\
                 patch.object(get_request_dispatch.native_read_routes, "handles", return_value=False), \\
                 patch.object(get_request_dispatch.operational_read_routes, "handles", return_value=False), \\
                 patch.object(get_request_dispatch.settings_read_routes, "handles", return_value=False), \\
                 patch.object(get_request_dispatch.history_read_routes, "handles", return_value=False):
                invoke(handler)
        self.assertEqual(handler.responses, [(404, {"error": "Not found."})])


if __name__ == "__main__":
    unittest.main()
