"""Real AI fallback orchestration with synthetic provider and HA transports."""
import io
import json
from pathlib import Path
import tempfile
from typing import Any
import unittest
from unittest.mock import Mock, patch

from ai_budget import monthly_reserved
from execution_results import Outcome
import history
from model_response_results import IncompletePlanningError, NonBillablePlanningError
from openai_planner import request_plan
import server


def completed(actions) -> dict[str, Any]:
    return {'status': 'completed', 'usage': {'input_tokens': 100, 'output_tokens': 20},
            'output': [{'type': 'message', 'role': 'assistant', 'content': [
                {'type': 'output_text', 'text': json.dumps({'actions': actions})}]}]}


class PlannerFixture(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(history, 'DATABASE', Path(directory) / 'history.sqlite3'))
        self.settings = {**server.ai_settings.DEFAULTS, 'enabled': True}
        self.inventory: list[dict[str, Any]] = [
            {'entity_id': 'light.study', 'state': 'off', 'attributes': {'friendly_name': 'Study'}},
            {'entity_id': 'light.private', 'state': 'off', 'attributes': {}},
            {'entity_id': 'script.secret', 'state': 'off', 'attributes': {}},
            {'entity_id': 'media_player.study', 'state': 'off', 'attributes': {}},
        ]
        self.payload = completed([{'entity_id': 'light.study', 'service': 'turn_on', 'depends_on': []}])
        self.provider, self.ha = Mock(), Mock()
        self.provider.open.side_effect = lambda *args, **kwargs: io.BytesIO(json.dumps(self.payload).encode())
        self.ha.open.side_effect = lambda *args, **kwargs: io.BytesIO(b'{"state":"on"}')
        self.enterContext(patch.object(server.ai_settings, 'read', return_value=self.settings))
        self.enterContext(patch.object(server, 'ha_device_connection', return_value=('http://ha', {}, self.ha)))
        self.enterContext(patch.object(server, 'read_ha_inventory_result', side_effect=lambda _: (self.inventory, None)))
        self.enterContext(patch.object(server.ai_credentials, 'get_key', return_value='synthetic-key'))
        self.enterContext(patch.object(server.openai_planner, 'build_opener', return_value=self.provider))

    def ask(self, utterance, exposed=('light.study',)):
        return server.guarded_openai_fallback_result(utterance, source='assist', exposed_entities=list(exposed))

    def spent(self):
        with history.database() as db:
            return monthly_reserved(db)


class PlannerContractTests(PlannerFixture):
    def test_implicit_command_reaches_real_planner_and_verified_dispatch(self):
        result = self.ask("it's too dark in here")
        self.assertIs(result.result.outcome, Outcome.CONFIRMED)
        self.assertEqual(self.provider.open.call_count, 1)
        self.assertEqual(self.ha.open.call_count, 2)
        body = json.loads(self.provider.open.call_args.args[0].data)
        self.assertEqual(body['text']['format']['schema']['properties']['actions']['maxItems'], 3)
        self.assertEqual(json.loads(body['input'])['allowed_entities'], ['light.study'])
        self.assertEqual(json.loads(self.ha.open.call_args_list[0].args[0].data), {'entity_id': 'light.study'})
        self.assertEqual(self.spent(), 65)

    def test_non_action_chat_produces_no_device_dispatch(self):
        self.payload = completed([])
        result = self.ask('tell me a joke')
        self.assertIs(result.result.outcome, Outcome.UNRESOLVED)
        self.assertEqual(result.result.actions, ())
        self.ha.open.assert_not_called()
        self.assertEqual(self.spent(), 65)

    def test_disabled_ai_and_missing_exposure_never_call_provider(self):
        self.settings['enabled'] = False
        self.assertIsNone(self.ask("it's too dark in here"))
        self.settings['enabled'] = True
        self.assertIs(self.ask("it's too dark in here", exposed=()).result.outcome, Outcome.UNRESOLVED)
        self.provider.open.assert_not_called()
        self.ha.open.assert_not_called()
        self.assertEqual(self.spent(), 0)

    def test_disallowed_domains_have_no_planning_request_or_reservation(self):
        result = self.ask('start the film', exposed=('script.secret', 'media_player.study'))
        self.assertIn('No permitted devices', result.result.reply)
        self.provider.open.assert_not_called()
        self.ha.open.assert_not_called()
        self.assertEqual(self.spent(), 0)

    def test_provider_cannot_escape_schema_exposure_or_service_contract(self):
        for entity, service in (('light.private', 'turn_on'), ('light.study', 'toggle'),
                                ('light.study', 'open_cover'), ('script.secret', 'turn_on')):
            with self.subTest(entity=entity, service=service):
                self.payload = completed([{'entity_id': entity, 'service': service, 'depends_on': []}])
                result = self.ask("it's too dark in here")
                self.assertIs(result.result.outcome, Outcome.UNRESOLVED)
                self.assertEqual(result.result.actions, ())
        self.ha.open.assert_not_called()
        self.assertEqual(self.spent(), 4 * 65)

    def test_sensitive_cover_stays_blocked_without_confirmation(self):
        self.inventory = [{'entity_id': 'cover.garage', 'state': 'closed', 'attributes': {'device_class': 'garage'}}]
        self.payload = completed([{'entity_id': 'cover.garage', 'service': 'open_cover', 'depends_on': []}])
        result = self.ask('the garage needs opening', exposed=('cover.garage',))
        self.assertIs(result.result.outcome, Outcome.UNRESOLVED)
        self.ha.open.assert_not_called()

    def test_incomplete_status_is_explained_and_settles_known_usage(self):
        self.payload = {'status': 'incomplete', 'incomplete_details': {'reason': 'max_output_tokens'},
                        'usage': {'input_tokens': 100, 'output_tokens': 20}, 'output': []}
        with self.assertLogs('openai_planner', level='WARNING') as logs:
            result = self.ask("it's too dark in here")
        self.assertIn('planning token limit', result.result.reply)
        self.assertIn('No devices were changed', result.result.reply)
        self.assertIn('reason=max_output_tokens', '\n'.join(logs.output))
        self.assertEqual(self.spent(), 65)
        self.ha.open.assert_not_called()

    def test_incomplete_unknown_reason_and_usage_stay_redacted_and_conservative(self):
        self.payload = {'status': 'incomplete', 'incomplete_details': {'reason': 'private-provider-secret'}, 'output': []}
        with self.assertLogs('openai_planner', level='WARNING') as logs:
            result = self.ask("it's too dark in here")
        self.assertIn("couldn't finish planning", result.result.reply)
        self.assertNotIn('private-provider-secret', result.result.reply + '\n'.join(logs.output))
        self.assertEqual(self.spent(), 50_000)
        self.ha.open.assert_not_called()


class ProviderSchemaTests(unittest.TestCase):
    def request(self, entities, *, model='gpt-5-mini', **kwargs):
        provider = Mock()
        provider.open.side_effect = lambda *args, **kw: io.BytesIO(json.dumps(completed([])).encode())
        self.assertEqual(request_plan('a fixture request', entities, opener=provider, model=model, api_key='fixture', **kwargs), ())
        return json.loads(provider.open.call_args.args[0].data)

    def test_schema_pairs_only_request_entities_and_supported_domain_services(self):
        body = self.request(['light.study', 'cover.blind', 'light.kitchen'])
        actions = body['text']['format']['schema']['properties']['actions']
        self.assertEqual(actions['maxItems'], 8)
        variants = actions['items']['anyOf']
        self.assertEqual(len(variants), 2)
        self.assertEqual(variants[0]['properties']['entity_id']['enum'], ['cover.blind'])
        self.assertEqual(variants[0]['properties']['service']['enum'], ['close_cover', 'open_cover'])
        self.assertEqual(variants[1]['properties']['entity_id']['enum'], ['light.kitchen', 'light.study'])
        self.assertEqual(variants[1]['properties']['service']['enum'], ['turn_off', 'turn_on'])
        for variant in variants:
            self.assertFalse(variant['additionalProperties'])
            self.assertEqual(set(variant['required']), {'entity_id', 'service', 'depends_on'})

    def test_low_effort_for_each_supported_priced_model(self):
        for model in ('gpt-5-mini', 'gpt-6-luna'):
            body = self.request(['light.study'], model=model)
            self.assertEqual(body['reasoning'], {'effort': 'low'})
            self.assertEqual(body['max_output_tokens'], 2000)

    def test_request_action_limit_is_applied_in_schema_and_local_validation(self):
        body = self.request(['light.study'], max_actions=1)
        self.assertEqual(body['text']['format']['schema']['properties']['actions']['maxItems'], 1)
        provider = Mock()
        actions = [{'entity_id': 'light.study', 'service': 'turn_on', 'depends_on': []}] * 2
        provider.open.return_value = io.BytesIO(json.dumps(completed(actions)).encode())
        with self.assertRaisesRegex(ValueError, 'Too many proposed actions'):
            request_plan('fixture', ['light.study'], opener=provider, model='gpt-5-mini', api_key='fixture', max_actions=1)

    def test_empty_context_is_a_zero_usage_local_noop(self):
        provider, usage = Mock(), Mock()
        result = request_plan('fixture', [], opener=provider, model='gpt-5-mini', api_key='fixture', usage_sink=usage)
        self.assertEqual(result, ())
        provider.open.assert_not_called()
        usage.assert_called_once_with({'input_tokens': 0, 'output_tokens': 0})

    def test_larger_output_allowance_remains_inside_pre_request_cost_check(self):
        provider = Mock()
        with self.assertRaises(NonBillablePlanningError):
            request_plan('fixture', ['light.study'], opener=provider, model='gpt-5-mini',
                         api_key='fixture', max_cost_micro_usd=4000)
        provider.open.assert_not_called()

    def test_incomplete_error_reason_rejects_untrusted_shapes(self):
        reason: object
        for reason in (None, [], {}, 'unknown private text'):
            self.assertEqual(IncompletePlanningError(reason).reason, 'unknown')
