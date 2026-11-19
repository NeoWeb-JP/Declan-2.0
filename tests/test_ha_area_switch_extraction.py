"""Regression tests for extracted HA area and switch-as-light boundaries."""
import json
import unittest
from unittest.mock import patch

import server
import ha_area_switch_actions as actions
from execution_results import Outcome


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return json.dumps(self.payload).encode()


class Opener:
    def __init__(self, *payloads):
        self.payloads = iter(payloads)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return Response(next(self.payloads))


class AreaSwitchExtractionTests(unittest.TestCase):
    def test_area_aliases_and_origin_template(self):
        opener = Opener([["Master Bedroom", ["light.bedroom"]], ["Study", ["light.study"]]])
        connection = ("https://ha.example", {}, opener)
        result = server.read_ha_areas(connection)
        self.assertEqual(result["bedroom"], {"light.bedroom"})
        self.assertEqual(result["office"], {"light.study"})
        self.assertEqual(opener.requests[0][1], 1.5)
        opener = Opener([["Living Room", ["light.lounge"]]])
        result = server.read_ha_areas(("https://ha.example", {}, opener), "satellite-1")
        self.assertEqual(result["lounge"], {"light.lounge"})
        self.assertIn("satellite-1", json.loads(opener.requests[0][0].data)["template"])

    def test_area_malformed_rows_are_rejected(self):
        for payload in (None, {}, [["Bedroom", "invalid"]], [[42, []]]):
            with self.subTest(payload=payload):
                self.assertEqual(server.read_ha_areas(
                    ("https://ha.example", {}, Opener(payload))), {})

    def test_unmarked_switch_is_never_dispatched(self):
        inventory = [{"entity_id": "switch.desk", "state": "off",
                      "attributes": {"friendly_name": "Desk"}}]
        opener = Opener()
        self.assertIsNone(server.set_switch_as_light_result(
            "desk", "on", inventory, ("https://ha.example", {}, opener)))
        self.assertEqual(opener.requests, [])

    def test_marked_switch_preview_and_confirmed_state(self):
        inventory = [{"entity_id": "switch.desk", "state": "off",
                      "attributes": {"friendly_name": "Desk", "declan_as_light": True}}]
        opener = Opener()
        connection = ("https://ha.example", {}, opener)
        preview = server.set_switch_as_light_result("desk", "on", inventory, connection, preview=True)
        self.assertIs(preview.outcome, Outcome.PREVIEW)
        self.assertEqual(opener.requests, [])
        opener = Opener({}, {"state": "on"})
        evidence = []
        result = server.set_switch_as_light_result(
            "desk", "on", inventory, ("https://ha.example", {}, opener),
            action_results=evidence)
        self.assertIs(result.outcome, Outcome.CONFIRMED)
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual([timeout for _, timeout in opener.requests], [4, 4])
        self.assertEqual(len(evidence), 1)

    def test_server_compatibility_passes_injected_request_and_evidence(self):
        with patch.object(server.ha_area_switch_actions, "set_switch_as_light_result",
                          return_value="sentinel") as extracted:
            result = server.set_switch_as_light_result(
                "desk", "on", [], ("url", {}, None), preview=True)
        self.assertEqual(result, "sentinel")
        self.assertIs(extracted.call_args.kwargs["request_factory"], server.Request)
        self.assertIs(extracted.call_args.kwargs["append_evidence"], server.append_action_evidence)


if __name__ == "__main__":
    unittest.main()
