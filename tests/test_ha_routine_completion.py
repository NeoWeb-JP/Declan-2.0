"""Verify that HA routine acknowledgements are not confused with execution."""
from typing import Any
from email.message import Message
import json
import unittest
from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import Mock, MagicMock, patch
from declan.ha import script_discovery


class RoutineResultTests(unittest.TestCase):
    def run_script(self, outcome, steps=None, recorded=None, reason=None):
        item: dict[str, Any]
        item = {"entity_id": "script.declan_local_good_morning",
                "name": "Declan - Good Morning - Shared Local Routine",
                "fields": ["request_id", "routine_id"], "safe": True}
        def open_request(request, timeout=None):
            payload = json.loads(request.data)
            self.assertIn("?return_response", request.full_url)
            self.assertEqual(payload["routine_id"], item["entity_id"])
            self.assertTrue(payload["request_id"].startswith("declan-"))
            result = {"service_response": {
                "outcome": outcome, "request_id": payload["request_id"],
                "routine_id": payload["routine_id"], "steps": steps or [], "reason_code": reason}}
            response = MagicMock()
            response.status = 200
            response.read.return_value = json.dumps(result).encode()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            return response
        opener = Mock()
        opener.open.side_effect = open_request
        with patch.object(script_discovery, "discover_result", return_value=script_discovery.DiscoveryResult(tuple([item]), None)):
            return script_discovery.execute(("http://ha", {}, opener), item, action_results=recorded)

    def test_personality_only_after_verified_completion(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / "declan/turn/response_composition.py").read_text()
        self.assertIn('decision_outcome is Outcome.REPORTED_SUCCESS', source)
        self.assertIn('verified or completed or parse_music(phrase)', source)
        self.assertIn('outcome=Outcome.CONFIRMED.value if verified or completed else outcome', source)
        self.assertIn('spoken = "Sorted." if verified else reply', source)
        self.assertIn('decorated = personality.decorate(', source)
        from declan.turn import personality_policy
        with patch.object(personality_policy.ROTATION.random, "choice", side_effect=lambda lines: lines[0]):
            success = personality_policy.decorate(
                "Good Morning completed successfully.", outcome="confirmed",
                guest=False, visitor_present=False)
            failed = personality_policy.decorate(
                "Good Morning could not be verified.", outcome="unverified",
                guest=False, visitor_present=False)
        self.assertNotEqual(success, "Good Morning completed successfully.")
        self.assertEqual(failed, "Good Morning could not be verified.")

    def test_unsupported_response_falls_back_once_without_claiming_success(self):
        item: dict[str, Any]
        item = {"entity_id": "script.declan_local_good_morning",
                "name": "Good Morning", "fields": ["request_id", "routine_id"]}
        calls = []
        def open_request(request, timeout=None):
            calls.append(request.full_url)
            if "?return_response" in request.full_url:
                raise HTTPError(request.full_url, 400, "Bad Request", Message(),
                                BytesIO(b'{"message":"Service does not support response data"}'))
            response = MagicMock()
            response.status = 200
            response.read.return_value = b"[]"
            response.__enter__.return_value = response
            return response
        opener = Mock()
        opener.open.side_effect = open_request
        with patch.object(script_discovery, "discover_result", return_value=script_discovery.DiscoveryResult(tuple([item]), None)):
            reply, outcome, _ = script_discovery.execute(("http://ha", {}, opener), item)
        self.assertEqual(len(calls), 2)
        self.assertEqual(outcome, "unverified")
        self.assertIn("does not support returning", reply)

    def test_other_400_never_retries_and_exposes_reason(self):
        item: dict[str, Any]
        item = {"entity_id": "script.declan_local_good_morning",
                "name": "Good Morning", "fields": []}
        opener = Mock()
        opener.open.side_effect = HTTPError(
            "http://ha", 400, "Bad Request", Message(),
            BytesIO(b'{"message":"extra keys not allowed @ data"}'))
        with patch.object(script_discovery, "discover_result", return_value=script_discovery.DiscoveryResult(tuple([item]), None)):
            reply, outcome, _ = script_discovery.execute(("http://ha", {}, opener), item)
        self.assertEqual(opener.open.call_count, 1)
        self.assertEqual(outcome, "failed")
        self.assertIn("extra keys not allowed", reply)

    def test_completed_steps(self):
        reply, outcome, _ = self.run_script("success", [
            {"required": True, "status": "confirmed"}])
        self.assertEqual(outcome, "reported_success")
        self.assertIn("completed successfully", reply)

    def test_queued_optional_music_does_not_block_required_lighting_success(self):
        recorded: list[dict[str, Any]]
        recorded = []
        steps = [{"target": "dining", "status": "confirmed", "required": True},
                 {"target": "dinner_music", "action": "request_playback", "status": "requested", "required": False}]
        self.assertEqual(self.run_script("success", steps, recorded)[1], "reported_success")
        self.assertEqual(recorded[1]["status"], "requested")
        import server
        self.assertEqual(server.routine_action_results_typed(recorded)[1].to_wire()["status"], "requested")
        failed: list[dict[str, Any]]
        failed = []
        self.assertEqual(self.run_script("success", [{**steps[0], "status": "unverified"}, steps[1]], failed)[1], "unverified")
        self.assertEqual(failed, [])

    def test_live_dinner_selection_carries_reply_category_without_hardcoded_entity(self):
        item: dict[str, Any]
        import server
        item = {"entity_id": "script.whatever_ha_calls_it", "name": "Declan - Dinner Is Served", "fields": [], "safe": True}
        with patch.object(server, "ha_device_connection", return_value=("http://ha", {}, Mock())), \
             patch.object(script_discovery, "discover_result", return_value=script_discovery.DiscoveryResult(tuple([item]), None)):
            for phrase in ("dinner time", "announce dinner", "run dinner is served"):
                kind, parameters = server.select_routine(phrase, None)
                self.assertEqual(kind, "auto:" + item["entity_id"])
                self.assertEqual(parameters["_declan_reply_category"], "dinner")

    def test_trace_completion_preserves_chained_action_outcomes(self):
        import server
        self.assertEqual(server.chained_outcome_result("execution_completed", "confirmed").value, "execution_completed")
        self.assertEqual(server.chained_outcome_result("execution_completed", "failed").value, "partial")

    def test_unknown_is_not_success(self):
        self.assertEqual(self.run_script("unknown")[1], "unverified")

    def test_known_movie_guard_reasons_are_spoken_clearly(self):
        reply, outcome, _ = self.run_script("unknown", reason="requested_action_missing_or_invalid")
        self.assertEqual(outcome, "unverified")
        self.assertIn("start, end or toggle", reply)
        self.assertNotIn("Shared Local Routine", reply)
        reply, outcome, _ = self.run_script("busy", reason="screen_moving")
        self.assertEqual(outcome, "busy")
        self.assertIn("still moving", reply)

    def test_partial_is_not_success(self):
        self.assertEqual(self.run_script("partial")[1], "partial")

    def test_guard_reasons_preserve_legacy_dispatch_boundaries(self):
        reason: object
        for outcome in ("unknown", "busy"):
            for reason, text in (("screen_moving", "still moving"),
                                 ("screen_position_unverified", "safe screen position"),
                                 ("requested_action_missing_or_invalid", "start, end or toggle")):
                reply, status, detail = self.run_script(outcome, reason=reason)
                self.assertIn(text, reply)
                self.assertEqual(status, "busy" if outcome == "busy" else "unverified")
                self.assertIsNone(detail)
            for reason in ("SCREEN_MOVING", " screen_moving", "future_reason", [], {}, None):
                self.assertEqual(self.run_script(outcome, reason=reason), self.run_script(outcome))
        for outcome in ("success", "partial", "failed", "cancelled", "started"):
            self.assertEqual(self.run_script(outcome, reason="screen_moving"), self.run_script(outcome))

    def test_busy_screen_is_not_an_unknown_outcome_or_success(self):
        reply, outcome, _ = self.run_script("busy")
        self.assertEqual(outcome, "busy")
        self.assertIn("already in progress", reply)

    def test_unconfirmed_required_step_rejects_success(self):
        self.assertEqual(self.run_script("success", [
            {"required": True, "status": "unverified"}])[1], "unverified")


if __name__ == "__main__":
    unittest.main()
