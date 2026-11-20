import io
import json
import unittest
from declan.ai.action_plan import CandidateAction
from declan.ha.ha_dispatcher import dispatch_result


class Opener:
    def __init__(self, states):
        self.states = iter(states)
        self.calls = []
    def open(self, request, timeout):
        self.calls.append(request.full_url)
        if "/api/services/" in request.full_url:
            return io.BytesIO(b"[]")
        return io.BytesIO(json.dumps({"state": next(self.states)}).encode())


class DispatcherTests(unittest.TestCase):
    def test_light_confirmed_after_readback(self):
        opener = Opener(["off", "on"])
        result = dispatch_result(CandidateAction("light.kitchen", "turn_on"),
                                 ("http://ha.local", {}, opener), authorised=lambda _: True,
                                   clock=lambda: 0, wait=lambda _: None)
        self.assertEqual(result.status.value, "confirmed")
        self.assertEqual(len(opener.calls), 3)

    def test_denied_never_dispatches(self):
        opener = Opener([])
        result = dispatch_result(CandidateAction("light.kitchen", "turn_on"),
                                 ("http://ha.local", {}, opener), authorised=lambda _: False)
        self.assertEqual(result.status.value, "failed")
        self.assertEqual(opener.calls, [])

    def test_script_acknowledgement_not_completion(self):
        opener = Opener([])
        result = dispatch_result(CandidateAction("script.goodnight", "turn_on"),
                                 ("http://ha.local", {}, opener), authorised=lambda _: True)
        self.assertEqual(result.status.value, "unverified")

    def test_no_readback_not_confirmed(self):
        opener = Opener(["off"])
        ticks = iter([0, 4])
        result = dispatch_result(CandidateAction("light.kitchen", "turn_on"),
                                 ("http://ha.local", {}, opener), authorised=lambda _: True,
                                   clock=lambda: next(ticks), wait=lambda _: None)
        self.assertEqual(result.status.value, "unverified")


if __name__ == "__main__":
    unittest.main()
