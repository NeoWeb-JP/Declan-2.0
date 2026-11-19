"""Area/floor aliases narrow trusted inventories without dropping group members."""
import copy
from email.message import Message
import io
import json
from typing import Any
import unittest
from urllib.error import HTTPError

from declan.ai.ai_context import ContextSelectionError, select
from execution_results import Outcome
from test_ai_planner_contract import PlannerFixture, completed


def catalogue():
    return {'areas': [
        {'id': 'living', 'name': 'Living Room', 'aliases': ['Lounge'], 'floor_id': 'ground'},
        {'id': 'kitchen', 'name': 'Kitchen', 'aliases': ['Cooking Room'], 'floor_id': 'ground'},
        {'id': 'other', 'name': 'Other', 'aliases': [], 'floor_id': 'upper'},
    ], 'floors': [
        {'id': 'ground', 'name': 'Ground Floor', 'aliases': ['Downstairs']},
        {'id': 'upper', 'name': 'Upper Floor', 'aliases': ['Upstairs']},
    ]}


def row(identifier, area, name='') -> dict[str, Any]:
    return {'entity_id': identifier, 'state': 'off', 'declan_area': area,
            'attributes': {'friendly_name': name or identifier}}


def inventory():
    return [row('light.a', 'Living Room', 'Reading Lamp'), row('light.b', 'Living Room'),
            row('light.c', 'Kitchen'), row('fan.a', 'Living Room')] + [
                row(f'switch.other_{index}', 'Other') for index in range(130)]


class AreaContextTests(unittest.TestCase):
    def setUp(self):
        self.rows = inventory()
        self.locations = catalogue()

    def ids(self, text, **kwargs):
        return [item['entity_id'] for item in select(self.rows, text, locations=self.locations, **kwargs)]

    def test_configured_alias_selects_the_complete_area_without_mutation(self):
        before = copy.deepcopy(self.rows)
        chosen = select(self.rows, 'the lounge is gloomy', locations=self.locations)
        self.assertEqual([item['entity_id'] for item in chosen], ['light.a', 'light.b', 'fan.a'])
        self.assertEqual(chosen[0]['declan_area_aliases'], ['Lounge'])
        self.assertEqual(chosen[0]['declan_floor'], 'Ground Floor')
        self.assertEqual(chosen[0]['declan_floor_aliases'], ['Downstairs'])
        self.assertEqual(self.rows, before)

    def test_floor_alias_and_domain_filter_select_every_requested_candidate(self):
        self.assertEqual(self.ids('all the lights downstairs off', max_actions=3), ['light.a', 'light.b', 'light.c'])
        self.assertEqual(self.ids('switch all the lights off', max_actions=3), ['light.a', 'light.b', 'light.c'])

    def test_multiple_areas_are_unioned_in_inventory_order(self):
        self.assertEqual(self.ids('turn the lounge and kitchen lights on'), ['light.a', 'light.b', 'light.c'])

    def test_duplicate_aliases_and_area_floor_collisions_require_clarification(self):
        self.locations['areas'][1]['aliases'] = ['Lounge']
        with self.assertRaisesRegex(ContextSelectionError, 'unique name'):
            self.ids('lounge lights on')
        self.locations = catalogue()
        self.locations['floors'][0]['aliases'] = ['Lounge']
        with self.assertRaisesRegex(ContextSelectionError, 'unique name'):
            self.ids('lounge lights on')

    def test_longest_location_phrase_does_not_include_a_shorter_area(self):
        self.locations['areas'].append({'id': 'outside', 'name': 'Outdoor Kitchen', 'aliases': [], 'floor_id': None})
        self.rows.append(row('light.outside', 'Outdoor Kitchen'))
        self.assertEqual(self.ids('outdoor kitchen lights on'), ['light.outside'])

    def test_area_name_changes_do_not_silently_drop_members(self):
        self.locations['areas'][0]['name'] = 'Renamed Living Room'
        with self.assertRaisesRegex(ContextSelectionError, 'metadata'):
            self.ids('downstairs lights on')

    def test_empty_requested_area_cannot_produce_a_partial_multi_area_plan(self):
        self.locations['areas'].append({'id': 'private', 'name': 'Private Room', 'aliases': [], 'floor_id': None})
        with self.assertRaisesRegex(ContextSelectionError, 'no permitted devices'):
            self.ids('living room and private room lights on')

    def test_exclusions_and_unknown_mixed_targets_never_reduce_to_one_room(self):
        for text in ('everything off except kitchen', 'living room and moon lights on'):
            with self.subTest(text=text), self.assertRaisesRegex(ContextSelectionError, 'separate commands'):
                self.ids(text)

    def test_group_and_owner_action_limits_refuse_instead_of_truncating(self):
        with self.assertRaisesRegex(ContextSelectionError, 'action limit'):
            self.ids('all downstairs lights on', max_actions=2)
        self.rows.extend(row(f'light.extra_{i}', 'Living Room') for i in range(101))
        with self.assertRaisesRegex(ContextSelectionError, 'too many devices'):
            self.ids('lounge lights on')

    def test_global_everything_over_limit_is_not_a_partial_plan(self):
        with self.assertRaisesRegex(ContextSelectionError, 'too many devices'):
            self.ids('everything off')

    def test_older_integration_keeps_exact_ids_names_and_canonical_areas(self):
        self.assertEqual([r['entity_id'] for r in select(self.rows, 'light.a on')], ['light.a'])
        self.assertEqual([r['entity_id'] for r in select(self.rows, 'reading lamp on')], ['light.a'])
        self.assertEqual([r['entity_id'] for r in select(self.rows, 'living room lights on')], ['light.a', 'light.b'])
        with self.assertRaisesRegex(ContextSelectionError, 'metadata'):
            select(self.rows, 'lounge lights on')

    def test_unexposed_explicit_entity_is_not_ignored_in_a_compound(self):
        with self.assertRaisesRegex(ContextSelectionError, 'no permitted devices'):
            self.ids('light.a and light.private on')

    def test_unicode_location_alias_is_matched_without_ascii_loss(self):
        self.locations['areas'][0]['aliases'] = ['Séjour']
        self.assertEqual(self.ids('sÉjour lights on'), ['light.a', 'light.b'])

    def test_malformed_or_inconsistent_registry_never_leaks_provider_details(self):
        malformed: object
        for malformed in ({}, {'areas': [], 'floors': 'private-secret'},
                          {'areas': [{'id': 'private-secret'}], 'floors': []}):
            with self.subTest(kind=type(malformed).__name__):
                with self.assertRaises(ContextSelectionError) as error:
                    select(self.rows, 'lounge lights on', locations=malformed)
                self.assertNotIn('private-secret', str(error.exception))
        self.locations['areas'][0]['floor_id'] = 'missing'
        with self.assertRaisesRegex(ContextSelectionError, 'metadata'):
            self.ids('lounge lights on')


class AreaContextDispatchTests(PlannerFixture):
    def setUp(self):
        super().setUp()
        self.inventory = inventory() + [row('light.private', 'Living Room')]
        self.locations = catalogue()
        self.exposed = tuple(item['entity_id'] for item in self.inventory if item['entity_id'] != 'light.private')
        self.location_error = False

        def ha_response(request, timeout):
            if request.full_url.endswith('/api/declan_two/ai-locations'):
                self.assertEqual(timeout, 1.5)
                if self.location_error:
                    raise HTTPError(request.full_url, 404, 'private-secret', Message(), io.BytesIO())
                return io.BytesIO(json.dumps(self.locations).encode())
            return io.BytesIO(b'{"state":"on"}')
        self.ha.open.side_effect = ha_response

    def test_floor_scope_reaches_real_planner_without_unexposed_devices(self):
        self.payload = completed([{'entity_id': entity, 'service': 'turn_on', 'depends_on': []}
                                  for entity in ('light.a', 'light.b', 'light.c')])
        result = self.ask('turn all the lights downstairs on', exposed=self.exposed)
        self.assertIs(result.result.outcome, Outcome.CONFIRMED)
        body = json.loads(self.provider.open.call_args.args[0].data)
        context = json.loads(body['input'])
        self.assertEqual(context['allowed_entities'], ['light.a', 'light.b', 'light.c'])
        self.assertEqual(context['current_state'][0]['area_aliases'], ['Lounge'])
        self.assertEqual(context['current_state'][0]['floor_aliases'], ['Downstairs'])
        self.assertNotIn('light.private', json.dumps(body))
        self.assertEqual(self.spent(), 65)
        self.assertEqual(self.ha.open.call_count, 7)  # Registry + three POST/readback pairs.

    def test_ambiguous_or_oversized_groups_do_not_reserve_or_call_openai(self):
        self.locations['areas'][1]['aliases'] = ['Lounge']
        result = self.ask('lounge lights on', exposed=self.exposed)
        self.assertIn('unique name', result.result.reply)
        self.locations = catalogue()
        self.settings['max_actions'] = 2
        result = self.ask('all downstairs lights on', exposed=self.exposed)
        self.assertIn('action limit', result.result.reply)
        self.provider.open.assert_not_called()
        self.assertEqual(self.spent(), 0)
        self.assertEqual(self.ha.open.call_count, 2)  # Only the two metadata reads.

    def test_metadata_failure_clarifies_alias_request_without_paid_planning(self):
        self.location_error = True
        result = self.ask('lounge lights on', exposed=self.exposed)
        self.assertIn('update the Declan integration', result.result.reply)
        self.assertNotIn('private-secret', result.result.reply)
        self.provider.open.assert_not_called()
        self.assertEqual(self.spent(), 0)

    def test_malformed_unhashable_exposure_is_denied_before_registry_lookup(self):
        for exposed in (({'entity_id': 'light.a'},), (['light.a'],), ('light.a', 'light.a')):
            with self.subTest(exposed=exposed):
                result = self.ask('lounge lights on', exposed=exposed)
                self.assertIn('permissions are unavailable', result.result.reply)
        self.ha.open.assert_not_called()
        self.provider.open.assert_not_called()
        self.assertEqual(self.spent(), 0)
