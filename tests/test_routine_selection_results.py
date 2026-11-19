"""Routine selection stays typed through preview and execution decisions."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from declan.turn.command_registry import RequestContext, routine_registry
from execution_results import ExecutionResult, Outcome
from declan.turn.routine_selection_results import RoutineSelection, RoutineSelectionKind, RoutineTurnSelection
from declan.ha import script_discovery
import server


class RoutineSelectionResultTests(unittest.TestCase):
    def test_legacy_selection_adapters_preserve_sentinels_and_detach_options(self):
        for key, expected in (("auto:script.tea", RoutineSelectionKind.SCRIPT),
                ("auto_ambiguous", RoutineSelectionKind.AMBIGUOUS),
                ("unconfigured_house_status", RoutineSelectionKind.HOUSE_STATUS_MISSING),
                ("old_mapping", RoutineSelectionKind.UNSUPPORTED)):
            with self.subTest(key=key):
                options = {"operation": "start", "extra": {"retained": True}}
                result = RoutineSelection.coerce((key, options))
                self.assertIs(result.kind, expected)
                self.assertEqual(result.as_legacy_pair(), (key, options))
                options["operation"] = "end"
                self.assertEqual(result.options["operation"], "start")
                legacy = result.as_legacy_pair()
                legacy[1]["extra"]["retained"] = False
                self.assertTrue(result.options["extra"]["retained"])
                self.assertEqual(deepcopy(result), result)
                with self.assertRaises(AttributeError):
                    setattr(result, "kind", RoutineSelectionKind.UNSUPPORTED)

    def test_selector_preview_and_execution_bypass_legacy_selection_apis(self):
        item = {"entity_id": "script.tea", "name": "Make Tea", "safe": True, "fields": []}
        with patch.object(server, "ha_device_connection", return_value="connection"), \
             patch.object(script_discovery, "discover_result", return_value=script_discovery.DiscoveryResult((item,))), \
             patch.object(server, "select_routine", side_effect=AssertionError("legacy selector")), \
             patch.object(server, "select_routine_turn", side_effect=AssertionError("legacy turn selector")), \
             patch.object(script_discovery, "execute_result", return_value=(ExecutionResult("Requested", Outcome.STARTED), None)) as execute:
            selected = server.select_routine_result("make tea", None)
            assert selected is not None
            self.assertIs(selected.kind, RoutineSelectionKind.SCRIPT)
            preview = server.preview_routine_result("make tea")
            self.assertIs(preview.outcome, Outcome.PREVIEW)
            execute.assert_not_called()
            result, _ = server.execute_routine_result(selected, [])
        self.assertIs(result.outcome, Outcome.STARTED)
        execute.assert_called_once_with("connection", {"entity_id": "script.tea"},
                                       parameters={}, expect_response=False, action_results=[])

    def test_registry_keeps_typed_execution_and_legacy_response_context(self):
        selected = RoutineSelection(RoutineSelectionKind.SCRIPT, "script.tea", {"operation": "start"})
        turn = RoutineTurnSelection(selected, "turn off kitchen")
        execute = Mock(return_value=(ExecutionResult("Requested", Outcome.STARTED), None))
        registry = routine_registry(select=Mock(return_value=turn), execute=execute, action_results=[], origin=None)
        response = registry.dispatch(RequestContext(phrase="make tea and turn off kitchen", source="assist"))
        assert response is not None
        execute.assert_called_once_with(selected, [])
        self.assertIs(execute.call_args.args[0], selected)
        self.assertEqual(response.routine_selection, turn.as_legacy_pair())
        self.assertEqual(response.routine_follow_on, "turn off kitchen")
        self.assertIs(response.result.outcome, Outcome.STARTED)

    def test_missing_ambiguous_and_unsupported_selections_never_execute(self):
        for kind, expected in ((RoutineSelectionKind.AMBIGUOUS, Outcome.UNRESOLVED),
                (RoutineSelectionKind.HOUSE_STATUS_MISSING, Outcome.NOT_CONFIGURED),
                (RoutineSelectionKind.UNSUPPORTED, Outcome.NOT_CONFIGURED)):
            selection = RoutineSelection(kind, legacy_key="missing")
            with self.subTest(kind=kind), patch.object(script_discovery, "execute_result") as execute, \
                 patch.object(script_discovery, "enqueue_result") as enqueue:
                result, _ = server.execute_routine_result(selection, [])
                self.assertIs(result.outcome, expected)
                self.assertEqual(server.execute_routine(selection.as_legacy_pair(), [])[1], expected.value)
            execute.assert_not_called()
            enqueue.assert_not_called()
