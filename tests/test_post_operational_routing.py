"""Operational POST routing keeps updater and validated routes distinct."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from declan.http import post_operational_routing


class OperationalPostRoutingTests(unittest.TestCase):
    def test_unknown_route_is_not_dispatched_before_validation(self):
        handler = SimpleNamespace(path="/api/chat")
        with patch.object(post_operational_routing.operational_post_dispatch, "handles_pre_validation", return_value=False), \
             patch.object(post_operational_routing.operational_post_dispatch, "dispatch_update") as dispatch:
            self.assertFalse(post_operational_routing.dispatch_before_validation(
                handler, {}, updates=SimpleNamespace(), release_version="test",
            ))
        dispatch.assert_not_called()

    def test_update_route_preserves_dependency_contract(self):
        handler = SimpleNamespace(path="/api/updates")
        updates = SimpleNamespace(check=MagicMock(), status_result=MagicMock(),
                                  prerelease_versions=MagicMock(), queue=MagicMock())
        with patch.object(post_operational_routing.operational_post_dispatch, "handles_pre_validation", return_value=True), \
             patch.object(post_operational_routing.operational_post_dispatch, "dispatch_update") as dispatch:
            self.assertTrue(post_operational_routing.dispatch_before_validation(
                handler, {"version": "test"}, updates=updates, release_version="test",
            ))
        dispatch.assert_called_once_with(
            handler, {"version": "test"}, check=updates.check,
            status_result=updates.status_result,
            prerelease_versions=updates.prerelease_versions,
            queue=updates.queue, release_version="test",
        )

    def test_unknown_route_is_not_dispatched_after_validation(self):
        handler = SimpleNamespace(path="/api/chat")
        with patch.object(post_operational_routing.operational_post_dispatch, "handles_after_validation", return_value=False), \
             patch.object(post_operational_routing.operational_post_dispatch, "dispatch_validated") as dispatch:
            self.assertFalse(post_operational_routing.dispatch_after_validation(
                handler, {}, message="hello", session_id="s",
                render=None, record=None, token_urlsafe=None, action_results=None,
            ))
        dispatch.assert_not_called()

    def test_validated_route_preserves_message_and_session(self):
        handler = SimpleNamespace(path="/api/assist/history")
        render, record, token, actions = (MagicMock() for _ in range(4))
        with patch.object(post_operational_routing.operational_post_dispatch, "handles_after_validation", return_value=True), \
             patch.object(post_operational_routing.operational_post_dispatch, "dispatch_validated") as dispatch:
            self.assertTrue(post_operational_routing.dispatch_after_validation(
                handler, {"message": "hello"}, message="hello", session_id="s",
                render=render, record=record, token_urlsafe=token, action_results=actions,
            ))
        dispatch.assert_called_once_with(
            handler, {"message": "hello"}, message="hello", session_id="s",
            render=render, record=record, token_urlsafe=token, action_results=actions,
        )


if __name__ == "__main__":
    unittest.main()
