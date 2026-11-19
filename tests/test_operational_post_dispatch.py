"""Verify operational POST dispatch and validation boundary."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from declan.http import operational_post_dispatch as routes


class OperationalPostDispatchTests(unittest.TestCase):
    def test_route_groups_are_disjoint(self):
        self.assertTrue(routes.handles_pre_validation("/api/updates"))
        self.assertFalse(routes.handles_after_validation("/api/updates"))
        for path in ("/api/tts", "/api/assist/history"):
            self.assertTrue(routes.handles_after_validation(path))
            self.assertFalse(routes.handles_pre_validation(path))

    def test_updates_delegate_before_message_validation(self):
        handler = SimpleNamespace(path="/api/updates")
        body = {"action": "check"}
        with patch.object(routes.operational_post_routes, "handle_updates") as delegate:
            routes.dispatch_update(handler, body, check=None, status_result=None,
                                   prerelease_versions=None, queue=None,
                                   release_version="test")
            delegate.assert_called_once()
            self.assertIs(delegate.call_args.args[1], body)
        handler.path = "/api/tts"
        with self.assertRaises(ValueError):
            routes.dispatch_update(handler, body, check=None, status_result=None,
                                   prerelease_versions=None, queue=None,
                                   release_version="test")

    def test_validated_routes_delegate(self):
        handler = SimpleNamespace(path="/api/tts")
        args = dict(message="hello", session_id="session", render=None,
                    record=None, token_urlsafe=None, action_results=None)
        with patch.object(routes.speech_http_routes, "render_tts") as delegate:
            routes.dispatch_validated(handler, {}, **args)
            delegate.assert_called_once_with(handler, "hello", render=None)
        handler.path = "/api/assist/history"
        with patch.object(routes.operational_post_routes, "handle_assist_history") as delegate:
            routes.dispatch_validated(handler, {"message": "hello"}, **args)
            delegate.assert_called_once()
            self.assertEqual(delegate.call_args.kwargs["session_id"], "session")
        handler.path = "/api/assist"
        with self.assertRaises(ValueError):
            routes.dispatch_validated(handler, {}, **args)


if __name__ == "__main__":
    unittest.main()
