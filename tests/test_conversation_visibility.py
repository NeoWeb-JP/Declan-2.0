"""Conversation cost and speed visibility: per-turn log, weekly summary, diagnostics."""
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from time import time
from unittest.mock import patch

from declan.ai import general_chat
from declan.core import history, understanding_quality
from declan.turn import conversation_turn
from declan.turn.command_vocabulary import UNMATCHED_REPLY

ROOT = Path(__file__).resolve().parents[1]
CONFIG = {"model": "gpt-5-mini", "profile": {"reasoning_effort": None, "input_usd_per_million": "0.25",
                                             "output_usd_per_million": "2.00"},
          "key": "sk", "monthly": 20_000_000, "ceiling": 50_000}
CONTEXT = {"you_are_in": "Office", "devices": [], "areas": {"Office"}, "music_rooms": set(), "routines": set()}


class VisibilityTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(history, "DATABASE", Path(folder) / "history.db"))
        self.enterContext(patch.dict(os.environ, {}, clear=True))

    def test_log_and_week_summary(self):
        now = datetime.now(timezone.utc)
        for kind, spent, ms, general in (("act", 300, 1200, False), ("ask", 200, 900, False),
                                         ("answer", 100, 700, True), ("failed", 50, 0, False)):
            general_chat.log_turn(kind, charged=spent, duration_ms=ms, general=general, now=now)
        general_chat.log_turn("bogus", charged=1, duration_ms=1, general=False, now=now)
        with history.database() as db:
            summary = general_chat.week_summary(db, now=time())
        self.assertEqual(summary, {"turns": 4, "act": 1, "answer": 1, "ask": 1, "failed": 1, "general_questions": 1,
                                   "spent_micro_usd": 650, "median_ms": 900})
        with history.database() as db:
            empty = general_chat.week_summary(db, now=time() - 30 * 86400)
        self.assertEqual(empty["turns"], 0)
        self.assertIsNone(empty["median_ms"])

    def test_understanding_summary_includes_conversation(self):
        general_chat.log_turn("answer", charged=120, duration_ms=800, general=True)
        result = understanding_quality.summary(unmatched_reply=UNMATCHED_REPLY, speaker_threshold=0.85)
        self.assertEqual(result["conversation"]["answer"], 1)
        self.assertEqual(result["conversation"]["spent_micro_usd"], 120)

    def fake_call(self, text):
        def call(body, *, usage=None, **kwargs):
            if usage is not None:
                usage.update(charged=111, duration_ms=650)
            if text is None:
                raise general_chat.ModelUnavailable("down")
            return text
        return call

    def test_decide_logs_each_turn_and_records_a_diagnostic_stage(self):
        reply = json.dumps({"kind": "answer", "say": "Lima.", "device_actions": [], "commands": []})
        with patch.object(general_chat, "call", side_effect=self.fake_call(reply)), \
                patch.object(conversation_turn.diagnostics, "record") as record:
            decision, _ = conversation_turn.decide("where is peru", CONTEXT, session_id="s", scope="o",
                                                   checks=(), config=CONFIG)
        self.assertEqual(decision.kind, "answer")
        self.assertEqual(record.call_args.args[0], "conversation_agent")
        self.assertEqual(record.call_args.kwargs["kind"], "answer")
        self.assertTrue(record.call_args.kwargs["general"])
        with patch.object(general_chat, "call", side_effect=self.fake_call(None)), \
                self.assertRaises(general_chat.ModelUnavailable):
            conversation_turn.decide("x", CONTEXT, session_id="s", scope="o", checks=(), config=CONFIG)
        with history.database() as db:
            kinds = [row[0] for row in db.execute("SELECT kind FROM conversation_log ORDER BY created_at")]
        self.assertEqual(kinds, ["answer", "failed"])

    def test_turns_that_never_reach_the_model_are_not_logged(self):
        def refuse(body, **kwargs):
            raise general_chat.ModelUnavailable("off")
        with patch.object(general_chat, "call", side_effect=refuse), self.assertRaises(general_chat.ModelUnavailable):
            conversation_turn.decide("x", CONTEXT, session_id="s", scope="o", checks=(), config=CONFIG)
        with history.database() as db:
            self.assertEqual(general_chat.week_summary(db, now=time())["turns"], 0)

    def test_call_reports_usage(self):
        import io
        db_path = Path(history.DATABASE)

        @contextmanager
        def database():
            with history.database() as db:
                yield db

        class Opener:
            def open(self, request, timeout):
                body = json.dumps({"status": "completed", "usage": {"input_tokens": 100, "output_tokens": 10},
                                   "output": [{"type": "message", "role": "assistant",
                                               "content": [{"type": "output_text", "text": "hi"}]}]}).encode()

                @contextmanager
                def response():
                    yield io.BytesIO(body)
                return response()
        from declan.ai import ai_pricing
        config = dict(CONFIG, profile=ai_pricing.model_profile("gpt-5-mini"))
        usage: dict = {}
        text = general_chat.call({"model": "gpt-5-mini", "input": "x", "max_output_tokens": 10}, config=config,
                                 settings={"enabled": True, "monthly_budget_usd": "20.00"}, opener=Opener(),
                                 database=database, usage=usage)
        self.assertEqual(text, "hi")
        self.assertGreater(usage["charged"], 0)
        self.assertIn("duration_ms", usage)
        self.assertTrue(db_path.exists())

    def test_proxy_and_panel(self):
        view = (ROOT / "custom_components/declan_two/history_view.py").read_text()
        self.assertIn('"conversation": conversation', view)
        js = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()
        self.assertIn("conversationSummary(data.conversation)", js)
        self.assertIn('class="understanding-conversation muted"', js)


if __name__ == "__main__":
    unittest.main()
