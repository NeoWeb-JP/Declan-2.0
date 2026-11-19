"""Authenticated registry projection and bounded backend transport behavior."""
from email.message import Message
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch
from urllib.error import HTTPError

from declan.ha import ha_inventory


class LocationViewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.web = SimpleNamespace(HTTPForbidden=type('Forbidden', (Exception,), {}),
            json_response=lambda payload, status=200, headers=None: {'payload': payload, 'status': status, 'headers': headers})
        self.areas = [SimpleNamespace(id='living', name='Living Room', aliases={'Lounge'}, floor_id='ground')]
        self.floors = [SimpleNamespace(floor_id='ground', name='Ground Floor', aliases={'Downstairs'})]
        self.area_registry = Mock()
        self.area_registry.async_get.return_value.async_list_areas.side_effect = lambda: iter(self.areas)
        self.floor_registry = Mock()
        self.floor_registry.async_get.return_value.async_list_floors.side_effect = lambda: iter(self.floors)
        self.enterContext(patch.dict('sys.modules', {
            'aiohttp': SimpleNamespace(web=self.web),
            'homeassistant': SimpleNamespace(), 'homeassistant.components': SimpleNamespace(),
            'homeassistant.components.http': SimpleNamespace(HomeAssistantView=object),
            'homeassistant.helpers': SimpleNamespace(area_registry=self.area_registry, floor_registry=self.floor_registry),
        }))
        path = Path(__file__).resolve().parents[1] / 'custom_components/declan_two/ai_locations_view.py'
        spec = importlib.util.spec_from_file_location('ai_locations_fixture', path)
        assert spec is not None and spec.loader is not None
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.view = self.module.DeclanAILocationsView()

    def request(self, user):
        class Request(dict):
            app = {'hass': object()}
        return Request(hass_user=user)

    async def test_non_admin_or_missing_user_cannot_read_registry(self):
        for user in (None, SimpleNamespace(is_admin=False)):
            with self.assertRaises(self.web.HTTPForbidden):
                await self.view.get(self.request(user))
        self.area_registry.async_get.assert_not_called()
        self.floor_registry.async_get.assert_not_called()

    async def test_authenticated_projection_uses_real_registry_aliases_and_no_entities(self):
        result = await self.view.get(self.request(SimpleNamespace(is_admin=True)))
        self.assertTrue(self.view.requires_auth)
        self.assertEqual(self.view.url, '/api/declan_two/ai-locations')
        self.assertEqual(result['status'], 200)
        self.assertEqual(result['headers'], {'Cache-Control': 'no-store'})
        self.assertEqual(result['payload'], {'areas': [
            {'id': 'living', 'name': 'Living Room', 'aliases': ['Lounge'], 'floor_id': 'ground'}],
            'floors': [{'id': 'ground', 'name': 'Ground Floor', 'aliases': ['Downstairs']}]})
        self.assertNotIn('entities', json.dumps(result['payload']))

    async def test_oversized_or_invalid_names_are_redacted_503_not_truncated(self):
        self.areas[0].aliases = {'private-secret-' + str(i) for i in range(33)}
        result = await self.view.get(self.request(SimpleNamespace(is_admin=True)))
        self.assertEqual(result['status'], 503)
        self.assertEqual(result['payload'], {'status': 'location_metadata_unavailable'})
        self.assertNotIn('private-secret', str(result))
        self.assertEqual(result['headers'], {'Cache-Control': 'no-store'})

    async def test_registry_count_limit_rejects_whole_projection(self):
        self.areas = self.areas * 1025
        result = await self.view.get(self.request(SimpleNamespace(is_admin=True)))
        self.assertEqual(result['status'], 503)
        self.assertNotIn('areas', result['payload'])


class LocationTransportTests(unittest.TestCase):
    def test_read_is_authenticated_bounded_get_with_no_retry(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"areas":[],"floors":[]}'
        opener = Mock()
        opener.open.return_value = response
        self.assertEqual(ha_inventory.read_locations(('http://ha', {'Authorization': 'Bearer fixture'}, opener)),
                         {'areas': [], 'floors': []})
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), 'GET')
        self.assertEqual(request.full_url, 'http://ha/api/declan_two/ai-locations')
        self.assertEqual(request.get_header('Authorization'), 'Bearer fixture')
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 1.5)
        response.read.assert_called_once_with(ha_inventory.MAX_PAGE_BYTES + 1)
        response.__exit__.assert_called_once()

    def test_bad_oversized_or_unavailable_payload_is_not_metadata(self):
        bodies = (b'[]', b'invalid', b'x' * (ha_inventory.MAX_PAGE_BYTES + 1))
        for body in bodies:
            opener = Mock()
            opener.open.return_value = io.BytesIO(body)
            self.assertIsNone(ha_inventory.read_locations(('http://ha', {}, opener)))
            opener.open.assert_called_once()
        for error in (TimeoutError('private-secret'), HTTPError('url', 404, 'private-secret', Message(), io.BytesIO())):
            opener = Mock()
            opener.open.side_effect = error
            self.assertIsNone(ha_inventory.read_locations(('http://ha', {}, opener)))
            opener.open.assert_called_once()
