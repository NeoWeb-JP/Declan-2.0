"""Caller and wire mutations must not change retained response payloads."""
import unittest
from dataclasses import replace

from execution_results import ExecutionResult, Outcome
from retry_cancellation import RetryCancellationResult
from turn_response import TurnResponse


class ResponsePayloadIsolationTests(unittest.TestCase):
    def factories(self):
        return (
            lambda payload: TurnResponse(payload, Outcome.CONFIRMED),
            lambda payload: RetryCancellationResult(
                ExecutionResult("Cancelled", Outcome.CANCELLED), payload),
        )

    def test_input_and_nested_wire_mutations_do_not_change_retained_response(self):
        for factory in self.factories():
            with self.subTest(factory=factory):
                payload = {"session_id": "session", "reply": "Done",
                           "steps": [{"detail": "Observed"}]}
                response = factory(payload)
                expected = response.to_wire()
                payload["session_id"] = "other-session"
                payload["steps"][0]["detail"] = "Changed input"
                wire = response.to_wire()
                self.assertEqual(wire, expected)
                wire["steps"][0]["detail"] = "Changed output"
                wire["session_id"] = "changed-output-session"
                self.assertEqual(response.to_wire(), expected)

    def test_replacement_and_metadata_adapter_keep_separate_payloads(self):
        response = TurnResponse({"session_id": "session", "reply": "Done",
                                 "steps": [{"detail": "Observed"}]}, Outcome.CONFIRMED)
        updated = replace(response, session_response=response.to_wire())

        def decorate(payload, **metadata):
            payload["steps"][0]["detail"] = "Decorated"

        decorated = updated.to_wire(decorate)
        self.assertEqual(decorated["steps"][0]["detail"], "Decorated")
        self.assertEqual(updated.to_wire()["steps"][0]["detail"], "Observed")
        self.assertEqual(response.to_wire()["steps"][0]["detail"], "Observed")


if __name__ == "__main__":
    unittest.main()
