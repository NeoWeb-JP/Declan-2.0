"""Typed discovery and matching preserve inspection, cache and selection rules."""
import io
import json
import unittest
from unittest.mock import Mock, patch

from declan.ha import script_discovery
import legacy_wire
import server


class DiscoveryContractTests(unittest.TestCase):
    def setUp(self):
        script_discovery.CACHE.clear()
        self.item = {"entity_id": "script.make_tea", "name": "Make Tea", "safe": False,
                     "fields": ["request_id", "routine_id"]}

    def connection(self, payload):
        opener = Mock()
        opener.open.side_effect = lambda *args, **kwargs: io.BytesIO(json.dumps(payload).encode())
        return "http://discovery-contract", {}, opener

    def test_discovery_core_cache_refresh_and_legacy_projection(self):
        connection = self.connection({"inspection": "complete", "scripts": [self.item]})
        with patch.object(script_discovery, "discover", side_effect=AssertionError("legacy roundtrip")):
            result = script_discovery.discover_result(connection)
            cached = script_discovery.discover_result(connection)
            self.assertIs(cached, result)
            self.assertEqual(connection[2].open.call_count, 1)
            refreshed = script_discovery.discover_result(connection, fresh=True)
        self.assertEqual(connection[2].open.call_count, 2)
        self.assertEqual(refreshed.scripts, (self.item,))
        self.assertIsNone(result.error)
        self.assertEqual(script_discovery.discover(connection), ([self.item], None))
        with self.assertRaises(AttributeError):
            setattr(result, "error", script_discovery.DiscoveryError.INVALID)

    def test_discovery_failure_vocabulary_and_validation(self):
        for payload, expected in (({}, script_discovery.DiscoveryError.INSPECTION_UNAVAILABLE),
                ({"inspection": "partial", "scripts": [self.item]}, script_discovery.DiscoveryError.INSPECTION_UNAVAILABLE),
                ({"inspection": "complete", "scripts": {}}, script_discovery.DiscoveryError.INVALID),
                ({"inspection": "complete", "scripts": [dict(self.item, safe="yes")]}, script_discovery.DiscoveryError.INVALID),
                ({"inspection": "complete", "scripts": [None] * 20001}, script_discovery.DiscoveryError.INVALID)):
            with self.subTest(expected=expected):
                connection = self.connection(payload)
                result = script_discovery.discover_result(connection)
                self.assertIs(result.error, expected)
                self.assertEqual(result.scripts, ())
                self.assertEqual(script_discovery.discover(connection), ([], expected.value))
        self.assertIs(script_discovery.discover_result(None).error, script_discovery.DiscoveryError.NOT_CONNECTED)
        self.assertIs(script_discovery.discover_result(("url", {}, None)).error,
                      script_discovery.DiscoveryError.INSPECTION_UNAVAILABLE)
        connection = self.connection({})
        connection[2].open.side_effect = TimeoutError()
        self.assertIs(script_discovery.discover_result(connection).error,
                      script_discovery.DiscoveryError.INSPECTION_UNAVAILABLE)

    def test_matching_is_typed_and_preserves_ambiguity_and_capability_preference(self):
        duplicate = dict(self.item, entity_id="script.other", fields=[])
        for phrase, scripts, expected in (("run make tea", [self.item], script_discovery.ScriptMatchStatus.MATCHED),
                ("make tea", [duplicate, self.item], script_discovery.ScriptMatchStatus.MATCHED),
                ("make tea", [self.item, dict(duplicate, fields=self.item["fields"])], script_discovery.ScriptMatchStatus.AMBIGUOUS),
                ("unknown", [self.item], script_discovery.ScriptMatchStatus.NO_MATCH)):
            with self.subTest(expected=expected):
                result = script_discovery.match_result(phrase, scripts)
                self.assertIs(result.status, expected)
                self.assertEqual(result.as_legacy_result(), script_discovery.match(phrase, scripts))
                if expected is script_discovery.ScriptMatchStatus.MATCHED:
                    self.assertIs(result.selected, self.item)
                else:
                    with self.assertRaises(ValueError):
                        _ = result.selected

    def test_selection_and_execution_do_not_use_legacy_discovery_or_matching(self):
        connection = self.connection({"inspection": "complete", "scripts": [self.item]})
        with patch.object(server, "ha_device_connection", return_value=connection), \
             patch.object(script_discovery, "discover", side_effect=AssertionError("legacy discovery")), \
             patch.object(script_discovery, "match", side_effect=AssertionError("legacy matching")):
            self.assertEqual(legacy_wire.select_routine("make tea", None), ("auto:script.make_tea", {}))
            result, _ = script_discovery.execute_result(connection, {"entity_id": "script.removed"})
        self.assertEqual(result.outcome.value, "unresolved")
