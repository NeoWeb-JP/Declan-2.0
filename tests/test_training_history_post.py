"""Contracts for training and history POST routing."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import training_history_post as routes


class TrainingHistoryPostTests(unittest.TestCase):
    def setUp(self):
        self.handler = SimpleNamespace(path="", send_json=lambda status, payload: self.responses.append((status, payload)))
        self.responses = []
        self.body = {"action": "test"}
        self.kwargs = dict(
            command_responses=object(), routine_responses=object(),
            discover=lambda: None, connection=lambda: None,
            history=SimpleNamespace(clear=lambda: None), voicepipeline=object(),
            unmatched_reply="unknown", forget_intent=lambda: None,
            edit_intent=lambda: None, teach_intent=lambda: None,
            storage_errors=(OSError,),
        )

    def test_allowlist_and_unknown(self):
        self.assertEqual(len(routes.ROUTES), 5)
        self.assertFalse(routes.handles("/api/updates"))
        self.handler.path = "/api/updates"
        with self.assertRaises(ValueError):
            routes.dispatch(self.handler, self.body, **self.kwargs)

    def test_retired_routines_still_gone(self):
        self.handler.path = "/api/native/routines"
        routes.dispatch(self.handler, self.body, **self.kwargs)
        self.assertEqual(self.responses[0][0], 410)

    def test_all_four_active_routes_delegate(self):
        cases = (
            ("/api/native/routine-responses", "native_training_post.handle_routine_responses"),
            ("/api/native/intents", "native_training_post.handle_native_intents"),
            ("/api/history/intents", "history_intents_post.handle_history_intents"),
            ("/api/history/clear", "history_post_routes.handle_history_clear"),
        )
        for path, target in cases:
            with self.subTest(path=path), patch.object(
                getattr(routes, target.split(".")[0]), target.split(".")[1],
            ) as delegate:
                self.handler.path = path
                routes.dispatch(self.handler, self.body, **self.kwargs)
                delegate.assert_called_once()
                self.assertIs(delegate.call_args.args[0], self.handler)
                self.assertIs(delegate.call_args.args[1], self.body)


if __name__ == "__main__":
    unittest.main()
