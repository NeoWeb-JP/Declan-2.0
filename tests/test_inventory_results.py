"""Shared typed inventory results retain paging, failures and legacy callbacks."""
import io
import json
import unittest
from unittest.mock import Mock, patch

from declan.ha import ha_inventory
from declan.music import music
import server
from execution_results import Outcome


class InventoryResultTests(unittest.TestCase):
    @staticmethod
    def row(index):
        return {'entity_id': f'light.test_{index}', 'state': 'on', 'attributes': {}}

    def connection(self, pages):
        opener = Mock()
        opener.open.side_effect = [io.BytesIO(json.dumps(page).encode()) for page in pages]
        return 'http://inventory-test', {}, opener

    def test_paged_core_returns_frozen_typed_inventory_without_legacy_roundtrip(self):
        rows = [self.row(index) for index in range(201)]
        connection = self.connection([{'total': 201, 'rows': rows[:200]}, {'total': 201, 'rows': rows[200:]}])
        with patch.object(ha_inventory, 'read', side_effect=AssertionError('legacy inventory')):
            result = server.read_ha_inventory_result(connection)
        self.assertIsNone(result.error)
        self.assertEqual(result.rows, tuple(rows))
        self.assertEqual(result.as_legacy_pair(), (rows, None))
        self.assertEqual(connection[2].open.call_count, 2)
        detached = result.inventory
        detached.clear()
        assert result.rows is not None
        self.assertEqual(len(result.rows), 201)
        with self.assertRaises(AttributeError):
            setattr(result, 'error', Outcome.UNAVAILABLE)

    def test_incomplete_changing_or_duplicate_inventory_is_typed_unavailable(self):
        cases = [[{'total': 1, 'rows': []}],
                 [{'total': 2, 'rows': [self.row(0), self.row(0)]}],
                 [{'total': 201, 'rows': [self.row(index) for index in range(200)]}, {'total': 202, 'rows': [self.row(200)]}],
                 [{'total': True, 'rows': []}]]
        for pages in cases:
            with self.subTest(pages=len(pages)):
                result = ha_inventory.read_result(self.connection(pages))
                self.assertIs(result.error, Outcome.UNAVAILABLE)
                self.assertIsNone(result.rows)
                self.assertEqual(result.as_legacy_pair(), (None, 'unavailable'))
        connection = self.connection([])
        connection[2].open.side_effect = TimeoutError('secret provider message')
        result = ha_inventory.read_result(connection)
        self.assertIs(result.error, Outcome.UNAVAILABLE)
        self.assertNotIn('secret', str(result))

    def test_legacy_adapters_and_callback_coercion_preserve_shapes(self):
        rows = [self.row(0)]
        self.assertEqual(ha_inventory.read(self.connection([{'total': 1, 'rows': rows}])), (rows, None))
        self.assertEqual(server.read_ha_inventory(self.connection([{'total': 0, 'rows': []}])), ([], None))
        self.assertEqual(server.read_music_inventory(self.connection([{'total': 0, 'rows': []}])), ([], None))
        typed = ha_inventory.InventoryResult.coerce((rows, None))
        self.assertIs(ha_inventory.InventoryResult.coerce(typed), typed)
        self.assertEqual(typed.inventory, rows)
        self.assertIs(ha_inventory.InventoryResult.coerce((None, 'unavailable')).error, Outcome.UNAVAILABLE)
        with self.assertRaises(ValueError):
            ha_inventory.InventoryResult.coerce(([], 'invalid_outcome'))

    def test_music_control_retries_typed_unavailable_inventory_once(self):
        reader = Mock(side_effect=[ha_inventory.InventoryResult(None, Outcome.UNAVAILABLE),
                                   ha_inventory.InventoryResult(())])
        with patch.dict('os.environ', {'DECLAN_ALLOW_UNCONFIGURED_MA': '1'}):
            result = music.control_result(('media_stop', None), ('http://ha', {}, Mock()), reader)
        self.assertEqual(reader.call_count, 2)
        self.assertIsInstance(result.outcome, Outcome)
