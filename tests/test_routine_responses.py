"""User response lists, persistence, selection, and concurrent editing."""
from typing import Any
from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
from unittest import TestCase
from unittest.mock import patch

import history
import routine_responses as responses
import personality_policy
import script_discovery
from execution_results import Outcome, parse_outcome


class RoutineResponsesTests(TestCase):
    def test_response_rendering_never_reads_another_credential_cache(self):
        live: dict[str, Any]
        live = {**self.item, "name": "Private script name", "fields": ["request_id"]}
        cached = script_discovery.DiscoveryResult((live,))
        cache = script_discovery.ScriptDiscoveryCache()
        key = cache.key("http://ha", {"Authorization": "Bearer other-token"})
        epoch = cache.begin(key)
        cache.publish(key, epoch, cached)
        with patch.object(script_discovery, "CACHE", cache), \
             patch.object(responses, "select", return_value="Custom line") as select:
            result = responses.render(("auto:" + live["entity_id"], {}), Outcome.STARTED, "Original")
        self.assertEqual(result, "Custom line")
        expected = {"entity_id": live["entity_id"], "name": "good morning"}
        select.assert_called_once_with(expected, "requested", False, "default")
        self.assertIs(type(select.call_args.args[1]), str)

    def test_typed_phase_selection_preserves_failure_diagnostics(self):
        for outcome in Outcome:
            with self.subTest(outcome=outcome), patch.object(responses, "select", return_value="Custom line"):
                selection: tuple[Any, ...]
                selection = ("auto:" + self.item["entity_id"], {})
                self.assertEqual(responses.render(selection, outcome, "Diagnostic"),
                                 responses.render(selection, outcome.value, "Diagnostic"))
                phase = responses.response_phase(outcome)
                if phase is responses.ResponsePhase.FAILURE:
                    self.assertEqual(responses.render(selection, outcome, "Diagnostic"), "Custom line Diagnostic")
        unknown: object
        for unknown in ("future_outcome", [], None):
            self.assertIsNone(parse_outcome(unknown))
            self.assertIsNone(responses.response_phase(unknown))
            self.assertEqual(responses.render(("auto:script.test", {}), unknown, "Original"), "Original")

    def setUp(self):
        folder = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(history, 'DATABASE', folder / 'history.db'))
        self.item = {'entity_id': 'script.good_morning', 'name': 'Declan - Good Morning'}

    def save(self, profile):
        return responses.save(self.item, profile, responses.snapshot(self.item)['expected'])

    def test_existing_lines_visible_and_selected_in_correct_mode(self):
        state = responses.snapshot(self.item)
        for mode, lines in [('sass', personality_policy._MORNING_HOME), ('guest', personality_policy._MORNING_GUEST)]:
            self.assertEqual(state['profile']['requested'][mode]['default'], ['Good morning. ' + line for line in lines])
            self.assertIn(responses.select(self.item, 'requested', mode == 'guest'), state['profile']['requested'][mode]['default'])

    def test_edits_additions_and_deletions_persist_across_selection(self):
        profile = responses.snapshot(self.item)['profile']
        profile['requested']['sass']['default'] = ['Edited response', 'Added response']
        profile['requested']['guest']['default'] = ['Welcome guests']
        self.save(profile)
        self.assertEqual(responses.snapshot(self.item)['profile'], profile)
        selected = [responses.select(self.item, 'requested', False) for _ in range(12)]
        self.assertEqual(set(selected), {'Edited response', 'Added response'})
        self.assertTrue(all(a != b for a, b in zip(selected, selected[1:])))
        self.assertEqual(responses.select(self.item, 'requested', True), 'Welcome guests')

    def test_empty_and_single_line_lists_do_not_resurrect_deleted_defaults(self):
        profile = responses.snapshot(self.item)['profile']
        profile['requested']['sass']['default'] = []
        self.save(profile)
        self.assertEqual(responses.select(self.item, 'requested', False), '')
        self.assertEqual(responses.render(('auto:script.good_morning', {}), 'started', 'Old sass'), 'Routine requested.')
        profile['requested']['sass']['default'] = ['Only line']
        self.save(profile)
        self.assertEqual([responses.select(self.item, 'requested', False) for _ in range(4)], ['Only line'] * 4)

    def test_directional_and_failure_lists_are_isolated(self):
        profile = responses.snapshot(self.item)['profile']
        profile['requested']['sass']['start'] = ['Starting']
        profile['requested']['sass']['end'] = ['Ending']
        profile['failure']['guest']['default'] = ['A guest failure line.']
        self.save(profile)
        selection = ('auto:script.good_morning', {'operation': 'end'})
        self.assertEqual(responses.render(selection, 'started', 'Original'), 'Ending')
        self.assertEqual(responses.render(selection, 'failed', 'Actual error.', guest=True), 'A guest failure line. Actual error.')
        self.assertEqual(responses.render(selection, 'partial', 'Partial detail.'), 'Partial detail.')
        self.assertEqual(responses.render(selection, 'confirmation_prompt', 'Confirm?'), 'Confirm?')

    def test_unknown_presence_is_passed_as_guest_and_other_scripts_stay_independent(self):
        profile = responses.snapshot(self.item)['profile']
        profile['requested']['sass']['default'] = ['Home only']
        profile['requested']['guest']['default'] = ['Guests only']
        self.save(profile)
        self.assertEqual(responses.render(('auto:script.good_morning', {}), 'started', 'Old', guest=True), 'Guests only')
        other = {'entity_id': 'script.other', 'name': 'Other'}
        self.assertNotEqual(responses.select(other, 'requested', False), 'Home only')

    def test_invalid_or_duplicate_lines_are_rejected_without_losing_saved_data(self):
        before = responses.snapshot(self.item)
        for lines in ([''], ['x' * 1001], ['same', ' same '], [1], ['\x00bad'], ['x'] * 101):
            profile = responses.snapshot(self.item)['profile']
            profile['completed']['sass']['default'] = lines
            with self.assertRaises(ValueError):
                responses.save(self.item, profile, before['expected'])
            self.assertEqual(responses.snapshot(self.item), before)

    def test_concurrent_edits_reject_stale_writer(self):
        initial = responses.snapshot(self.item)
        def edit(line):
            import copy
            profile = copy.deepcopy(initial['profile'])
            profile['requested']['sass']['default'] = [line]
            try:
                responses.save(self.item, profile, initial['expected'])
                return 'saved'
            except ValueError:
                return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(edit, ['First', 'Second']))
        self.assertCountEqual(results, ['saved', 'conflict'])

    def test_informational_responses_preserved_until_explicitly_edited(self):
        selection = ('auto:script.good_morning', {'_declan_expect_response': True})
        self.assertEqual(responses.render(selection, 'execution_completed', 'Current house status'), 'Current house status')
        profile = responses.snapshot(self.item)['profile']
        profile['completed']['sass']['default'] = ['Custom status acknowledgement']
        self.save(profile)
        self.assertEqual(responses.render(selection, 'execution_completed', 'Current house status'), 'Custom status acknowledgement')
