"""Configurable household entity validation and guest dispatch regressions."""

from typing import Any
import json
import unittest
from unittest.mock import Mock, patch

import configuration
from declan.ha import household_entities
import server
from execution_results import Outcome


class HouseholdEntitiesTests(unittest.TestCase):
    def test_defaults_keep_existing_installations_working(self):
        with patch.object(household_entities.configuration, "get",
                          side_effect=lambda key, default: default):
            self.assertEqual(household_entities.guest_mode(), "input_boolean.guest_mode")
            self.assertEqual(household_entities.guest_register(), "input_text.guests_in_charge")
            self.assertEqual(household_entities.projector_power(), "switch.projector_power_socket")

    def test_custom_native_settings_and_domain_validation(self):
        mapping = {
            "DECLAN_GUEST_MODE_ENTITY": "input_boolean.visitor_authority",
            "DECLAN_GUEST_REGISTER_ENTITY": "input_text.house_sitters",
            "DECLAN_PROJECTOR_POWER_ENTITY": "switch.movie_projector",
        }
        with patch.object(household_entities.configuration, "get",
                          side_effect=lambda key, default: mapping.get(key, default)):
            self.assertEqual(household_entities.guest_mode(), "input_boolean.visitor_authority")
            self.assertEqual(household_entities.guest_register(), "input_text.house_sitters")
            self.assertEqual(household_entities.projector_power(), "switch.movie_projector")
        for key, domain in (
            ("DECLAN_GUEST_MODE_ENTITY", "switch"),
            ("DECLAN_GUEST_REGISTER_ENTITY", "input_boolean"),
            ("DECLAN_PROJECTOR_POWER_ENTITY", "light"),
        ):
            with self.subTest(key=key), patch.object(
                household_entities.configuration, "get", return_value=domain + ".bad"
            ):
                with self.assertRaises(ValueError):
                    household_entities.resolve(key, "input_boolean" if key.endswith("MODE_ENTITY")
                                               else "input_text" if key.endswith("REGISTER_ENTITY")
                                               else "switch", "")

    def test_settings_import_validates_entity_domains(self):
        doc: dict[str, Any]
        doc = {"format": "declan-settings", "schema_version": 1, "settings": {
            "DECLAN_GUEST_MODE_ENTITY": "input_boolean.visitor_authority",
            "DECLAN_GUEST_REGISTER_ENTITY": "input_text.house_sitters",
            "DECLAN_PROJECTOR_POWER_ENTITY": "switch.movie_projector",
        }}
        self.assertIs(configuration.validate(doc), doc)
        for key in doc["settings"]:
            modified = {"format": "declan-settings", "schema_version": 1, "settings":
                        {**doc["settings"], key: "sensor.invalid"}}
            with self.subTest(key=key), self.assertRaises(ValueError):
                configuration.validate(modified)

    def test_guest_operation_uses_configured_entities_in_service_payloads(self):
        status = {
            "input_text.house_sitters": "Mike and Kathy",
            "input_boolean.visitor_authority": "on",
        }
        sent = []

        class Response:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, limit):
                return json.dumps(self.payload).encode()

        class Opener:
            def open(self, req, timeout):
                sent.append(req)
                if "/api/states/" in req.full_url:
                    entity = req.full_url.split("/api/states/", 1)[1]
                    return Response({"state": status.get(entity, "unknown")})
                return Response({})

        with patch.object(household_entities, "guest_mode", return_value="input_boolean.visitor_authority"), \
             patch.object(household_entities, "guest_register", return_value="input_text.house_sitters"):
            result = server.guest_assignment_result(
                "assign:Mike and Kathy", ("http://ha", {}, Opener()))
        self.assertIs(result.outcome, Outcome.CONFIRMED)
        calls = [json.loads(req.data) for req in sent if req.data]
        self.assertEqual(calls, [
            {"entity_id": "input_text.house_sitters", "value": "Mike and Kathy"},
            {"entity_id": "input_boolean.visitor_authority"},
        ])
        self.assertNotIn("input_boolean.guest_mode", str(calls))

    def test_invalid_guest_setting_fails_closed_before_home_assistant_writes(self):
        opener = Mock()
        with patch.object(household_entities, "guest_mode", side_effect=ValueError("bad")):
            result = server.guest_assignment_result("clear", ("http://ha", {}, opener))
        self.assertIs(result.outcome, Outcome.NOT_CONFIGURED)
        opener.open.assert_not_called()


if __name__ == "__main__":
    unittest.main()
