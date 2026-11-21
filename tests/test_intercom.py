"""FUT-25: one-way intercom and broadcast through assist_satellite.announce."""
import json
import unittest
from types import SimpleNamespace

from declan.core.execution_results import Outcome
from declan.ha import intercom
from declan.turn import turn_http_entry

ROWS = [["assist_satellite.kitchen", "Kitchen", "Ground floor", "idle", "dev-k"],
        ["assist_satellite.lounge", "Lounge", "Ground floor", "idle", "dev-l"],
        ["assist_satellite.master_bedroom", "Master Bedroom", "First floor", "idle", "dev-m"],
        ["assist_satellite.utility", "Utility Room", "Ground floor", "unavailable", "dev-u"]]


class Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return json.dumps(self.body).encode()


class FakeHA:
    def __init__(self, fail=()):
        self.announced = []
        self.fail = fail

    def open(self, request, timeout=None):
        data = json.loads(request.data)
        if request.full_url.endswith("/api/template"):
            return Response(ROWS)
        if data["entity_id"] in self.fail:
            raise OSError("offline")
        self.announced.append((data["entity_id"], data["message"]))
        return Response([])


class IntercomTests(unittest.TestCase):
    def say(self, phrase, origin="dev-l", ha=None, quiet=False):
        ha = ha or FakeHA()
        result = intercom.result(intercom.match(phrase), ("http://ha", {}, ha), origin=origin, quiet=quiet)
        return result, ha.announced

    def test_tell_one_room(self):
        result, announced = self.say("tell the kitchen dinner's ready")
        self.assertEqual((result.reply, result.outcome), ("Told the kitchen.", Outcome.CONFIRMED))
        self.assertEqual(announced, [("assist_satellite.kitchen", "Message from the lounge: dinner's ready.")])
        _, announced = self.say("announce to the master bedroom: breakfast is ready")
        self.assertEqual(announced, [("assist_satellite.master_bedroom", "Message from the lounge: breakfast is ready.")])

    def test_everyone_skips_the_asking_room_and_reports_unreachable_ones(self):
        result, announced = self.say("announce to everyone: leaving in five minutes")
        self.assertEqual([entity for entity, _ in announced],
                         ["assist_satellite.kitchen", "assist_satellite.master_bedroom"])
        self.assertEqual((result.reply, result.outcome), ("Told everyone. I couldn't reach Utility Room.", Outcome.PARTIAL))
        result, _ = self.say("tell everyone the taxi is here", ha=FakeHA(fail={"assist_satellite.kitchen"}))
        self.assertIn("Kitchen", result.reply)

    def test_floors(self):
        _, announced = self.say("announce upstairs bedtime")
        self.assertEqual(announced, [("assist_satellite.master_bedroom", "Message from the lounge: bedtime.")])

    def test_quiet_hours_and_unknown_rooms(self):
        result, announced = self.say("tell the kitchen dinner's ready", quiet=True)
        self.assertEqual((result.outcome, announced), (Outcome.UNRESOLVED, []))
        self.assertIsNone(self.say("tell me a joke")[0])
        self.assertIsNone(self.say("tell the garage hello")[0])
        self.assertIn("nobody else", self.say("tell the lounge hello")[0].reply)
        self.assertIsNone(intercom.match("announce"))

    def test_request_flow(self):
        services = SimpleNamespace(ha_device_connection=lambda: ("http://ha", {}, FakeHA()))
        self.assertIsNone(turn_http_entry._intercom(intercom.match("tell me a joke"), services, "dev-l"))
        result = turn_http_entry._intercom(intercom.match("tell the kitchen hi"), services, "dev-l")
        self.assertIn(result.outcome, {Outcome.CONFIRMED, Outcome.UNRESOLVED})  # depends on the real clock's quiet hours


if __name__ == "__main__":
    unittest.main()
