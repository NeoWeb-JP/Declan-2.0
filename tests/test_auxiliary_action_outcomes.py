"""Auxiliary actions keep typed outcomes without retrying uncertain requests."""
from typing import Any, cast
import io
import json
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import Mock, patch

from declan.turn import roast_guest_dispatch
import server
from execution_results import ExecutionResult, Outcome, MovieLaunchResult, MovieLaunchStatus


class AuxiliaryActionOutcomeTests(unittest.TestCase):
    def test_movie_launch_preserves_acceptance_without_claiming_confirmation(self):
        opener = Mock()
        opener.open.side_effect = [io.BytesIO(b'{"state":"on"}'), io.BytesIO(b'[]')]
        with patch.object(server, "launch_movie_app", side_effect=AssertionError("legacy launch")):
            result = server.launch_movie_app_result(("http://ha", {}, opener), "remote.tv", ("TV", "tv"))
        self.assertIs(result.status, MovieLaunchStatus.SENT)
        self.assertEqual(opener.open.call_count, 2)
        self.assertEqual(json.loads(opener.open.call_args.args[0].data)["delay_secs"], 2)
        self.assertIs(type(result.as_legacy_pair()[0]), str)
        with self.assertRaises(FrozenInstanceError):
            result.detail = "changed"

    def test_movie_launch_skips_unavailable_and_never_retries_timeout(self):
        for response, expected, calls in (
                ([io.BytesIO(b'{"state":"unavailable"}')], MovieLaunchStatus.SKIPPED, 1),
                ([io.BytesIO(b'{"state":"on"}'), TimeoutError()], MovieLaunchStatus.UNVERIFIED, 2)):
            opener = Mock()
            opener.open.side_effect = response
            result = server.launch_movie_app_result(("http://ha", {}, opener), "remote.tv", ("TV", "tv"))
            self.assertIs(result.status, expected)
            self.assertEqual(opener.open.call_count, calls)

    def test_movie_launch_rejects_invalid_status_and_detail(self):
        for status, detail in (("confirmed", "detail"), ("sent", None)):
            with self.assertRaises(ValueError):
                cast(Any, MovieLaunchResult)(status, detail)

    def test_dinner_quiet_hours_remain_typed_skipped_without_dispatch(self):
        opener = Mock()
        with patch.object(server.personality_policy, "overnight_announcement_allowed", return_value=False):
            result = server.start_dinner_result(("http://ha", {}, opener))
            legacy = server.start_dinner(("http://ha", {}, opener))
        self.assertIs(result.outcome, Outcome.SKIPPED)
        self.assertEqual(legacy, result.as_legacy_pair())
        self.assertIs(type(legacy[1]), str)
        opener.open.assert_not_called()

    def test_dinner_receipt_and_uncertain_request_remain_distinct(self):
        for response, expected in ((io.BytesIO(b'[]'), Outcome.REQUESTED), (TimeoutError(), Outcome.UNVERIFIED)):
            opener = Mock()
            opener.open.side_effect = [response]
            with patch.object(server.personality_policy, "overnight_announcement_allowed", return_value=True), \
                 patch.object(server.routine_registry, "load", return_value={"dinner": {"script": "script.dinner", "sensitive": False}}), \
                 patch.object(server, "read_guest_mode", return_value="off"):
                result = server.start_dinner_result(("http://ha", {}, opener))
            self.assertIs(result.outcome, expected)
            opener.open.assert_called_once()

    def test_guest_dispatch_accepts_typed_result_and_preserves_plain_strings(self):
        provider = Mock(return_value=ExecutionResult("Updated", Outcome.CONFIRMED))
        result = roast_guest_dispatch.dispatch_roast_or_guest(
            "guests", roast_target=lambda _: None, respond_to_roast=Mock(),
            guest_mode=Mock(), visitors_present=Mock(), response_guest_mode=Mock(),
            roast_respond=Mock(), assignment_action=lambda *_: "check", guest_commands={},
            guest_assignment=provider, connection=lambda: "ha")
        self.assertEqual(result, ("Updated", "confirmed"))
        self.assertIs(type(result[1]), str)
        provider.assert_called_once_with("check", "ha")

    def test_switch_fallback_core_and_legacy_unmatched_preview_contracts(self):
        row = {"entity_id": "switch.garden", "state": "off", "attributes": {
            "declan_as_light": True, "friendly_name": "Garden light"}}
        typed = server.set_switch_as_light_result("garden light", "on", [row], None, preview=True)
        self.assertIs(typed.outcome, Outcome.PREVIEW)
        self.assertEqual(server.set_switch_as_light("garden light", "on", [row], None, preview=True), typed.as_legacy_pair())
        self.assertIsNone(server.set_switch_as_light_result("missing", "on", [row], None))
        self.assertIsNone(server.set_switch_as_light("missing", "on", [row], None))

    def test_lighting_fallback_bypasses_legacy_switch_provider(self):
        expected = ExecutionResult("Already on", Outcome.CONFIRMED)
        with patch.object(server, "ha_device_connection", return_value=("http://ha", {}, Mock())), \
             patch.object(server, 'read_ha_inventory_result', return_value=([], None)), \
             patch.object(server, "read_ha_areas", return_value={}), \
             patch.object(server, "set_switch_as_light", side_effect=AssertionError("legacy switch")), \
             patch.object(server, "set_switch_as_light_result", return_value=expected) as switch:
            self.assertIs(server.set_lights_result("garden light", "on"), expected)
        switch.assert_called_once()

    def test_guest_legacy_adapter_preserves_plain_strings(self):
        with patch.object(server, "guest_assignment_result", return_value=ExecutionResult("Cannot verify", Outcome.UNVERIFIED)):
            result = server.guest_assignment("clear", None)
        self.assertEqual(result, ("Cannot verify", "unverified"))
        self.assertIs(type(result[1]), str)


if __name__ == "__main__":
    unittest.main()
