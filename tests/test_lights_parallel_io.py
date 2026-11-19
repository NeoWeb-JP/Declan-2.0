"""Independent light service calls and state reads run concurrently, results stay ordered."""
import os
import threading
import unittest
from unittest.mock import patch

import server
import test_home_assistant as fixtures
from declan.ha.lighting_execution_dispatch import concurrently


class ConcurrentlyTests(unittest.TestCase):
    def test_preserves_order_and_runs_items_at_once(self):
        barrier = threading.Barrier(3, timeout=2)

        def work(item):
            barrier.wait()  # only passes if all three run at the same time
            return item * 2

        self.assertEqual(concurrently(work, [1, 2, 3]), [2, 4, 6])

    def test_single_item_runs_inline(self):
        seen = []
        concurrently(lambda item: seen.append(threading.current_thread()), [1])
        self.assertEqual(seen, [threading.current_thread()])

    def test_empty(self):
        self.assertEqual(concurrently(lambda item: item, []), [])


class GatedHomeAssistant(fixtures.FakeHomeAssistant):
    """Blocks matching requests until `parties` of them are in flight together."""

    def __init__(self, prefix, parties):
        super().__init__()
        self.prefix, self.barrier = prefix, threading.Barrier(parties, timeout=3)
        self.gated = 0

    def open(self, request, timeout):
        if request.full_url.split("?")[0].split("/api", 1)[1].startswith(self.prefix):
            self.gated += 1
            self.barrier.wait()
        return super().open(request, timeout)


class LightsParallelTests(unittest.TestCase):
    def run_with(self, ha, phrase):
        self.enterContext(patch.dict(os.environ, fixtures.HA_ENV))
        self.enterContext(patch.object(server, "build_opener", return_value=ha))
        return server.handle_light_request(phrase, action_results=[])

    def test_mixed_directions_are_sent_together(self):
        ha = GatedHomeAssistant("/services/light/turn_", 2)
        reply, outcome = self.run_with(ha, "turn on the study light and turn off the fairy lights")
        self.assertEqual(outcome, "confirmed", reply)
        self.assertEqual((ha.entities["light.study_light"]["state"], ha.entities["light.fairy_lights"]["state"]),
                         ("on", "off"))

    def test_pending_lights_are_checked_together(self):
        ha = GatedHomeAssistant("/states/light.", 2)
        ha.entities["light.study_light"]["state"] = "off"
        ha.entities["light.bedroom_lamp"]["state"] = "off"
        reply, outcome = self.run_with(ha, "turn on the study light and the bedroom lamp")
        self.assertEqual(outcome, "confirmed", reply)

    def test_one_failed_call_does_not_hide_the_other(self):
        ha = fixtures.FakeHomeAssistant()
        ha.fail = "/api/services/light/turn_on"
        reply, outcome = self.run_with(ha, "turn on the study light and turn off the fairy lights")
        self.assertEqual(outcome, "partial", reply)
        self.assertEqual(ha.entities["light.fairy_lights"]["state"], "off")
        self.assertIn("HTTP 503", reply)


if __name__ == "__main__":
    unittest.main()
