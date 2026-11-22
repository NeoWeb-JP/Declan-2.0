"""FUT-33: ring a household phone through the Home Assistant companion app."""
import json
import unittest
from email.message import Message
from types import SimpleNamespace
from urllib.error import HTTPError

from declan.core.execution_results import Outcome
from declan.ha import find_phone
from declan.turn import house_questions, turn_http_entry

PEOPLE = [["person.jaco", "Jaco", [["device_tracker.pixel_8", "Pixel 8", "Google"]]],
          ["person.edd", "Edd", [["device_tracker.edd_iphone", "iPhone15,2", "Apple"]]],
          ["person.gran", "Gran", []]]


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
    def __init__(self, people=None, missing=()):
        self.people = PEOPLE if people is None else people
        self.missing = missing
        self.sent = []

    def open(self, request, timeout=None):
        if request.full_url.endswith("/api/template"):
            return Response(self.people)
        service = request.full_url.rsplit("/", 1)[1]
        if service in self.missing:
            raise HTTPError(request.full_url, 400, "Service not found", Message(), None)
        self.sent.append((service, json.loads(request.data)))
        return Response([])


def ring(phrase, **fake):
    ha = FakeHA(**fake)
    return find_phone.result(find_phone.match(phrase), ("http://ha", {}, ha)), ha


class FindPhoneTests(unittest.TestCase):
    def test_phrases(self):
        cases = {"ring Edd's phone": ("ring", "edd"), "find my phone": ("ring", None),
                 "I can't find my phone": ("ring", None), "can you ring Jaco's mobile": ("ring", "jaco"),
                 "Edd can't find his phone": ("ring", "edd"), "I've lost my phone": ("ring", None),
                 "Declan, ring my phone please": ("ring", None)}
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(find_phone.match(phrase), expected)
        for other in ("where's my phone", "have you seen my phone", "call mom", "ring the bell", None):
            with self.subTest(phrase=other):
                self.assertIsNone(find_phone.match(other))

    def test_rings_the_companion_app_loudly(self):
        result, ha = ring("ring Jaco's phone")
        self.assertEqual((result.reply, result.outcome), ("Ringing Jaco's phone. Follow the noise.", Outcome.REQUESTED))
        service, payload = ha.sent[0]
        self.assertEqual(service, "mobile_app_pixel_8")
        self.assertEqual(payload["data"]["channel"], "alarm_stream")
        self.assertEqual(payload["data"]["push"]["sound"]["critical"], 1)

    def test_iphone_gets_the_critical_alerts_reminder(self):
        result, ha = ring("ring Edd's phone")
        self.assertEqual(ha.sent[0][0], "mobile_app_edd_iphone")
        self.assertIn("critical alerts", result.reply)

    def test_my_phone_with_one_phone_or_several(self):
        result, ha = ring("find my phone", people=PEOPLE[:1])
        self.assertEqual(ha.sent[0][0], "mobile_app_pixel_8")
        result, ha = ring("find my phone")
        self.assertEqual((result.outcome, ha.sent), (Outcome.UNRESOLVED, []))
        self.assertIn("Whose phone", result.reply)
        result, _ = ring("find my phone", people=PEOPLE[2:])
        self.assertEqual(result.outcome, Outcome.NOT_CONFIGURED)

    def test_unknown_person_no_phone_and_unreachable_phone(self):
        self.assertEqual(ring("ring Bob's phone")[0].outcome, Outcome.UNRESOLVED)
        self.assertEqual(ring("ring Gran's phone")[0].outcome, Outcome.NOT_CONFIGURED)
        result, _ = ring("ring Edd's phone", missing={"mobile_app_edd_iphone"})
        self.assertEqual(result.outcome, Outcome.FAILED)
        self.assertIn("couldn't reach Edd's phone", result.reply)

    def test_home_assistant_unavailable(self):
        self.assertEqual(find_phone.result(("ring", "edd"), None).outcome, Outcome.NOT_CONFIGURED)

        class Down:
            def open(self, request, timeout=None):
                raise OSError("down")
        self.assertEqual(find_phone.result(("ring", "edd"), ("http://ha", {}, Down())).outcome, Outcome.UNAVAILABLE)

    def test_through_the_turn_entry(self):
        ha = FakeHA()
        services = SimpleNamespace(read_guest_mode=lambda: "on", ha_device_connection=lambda: ("http://ha", {}, ha))
        request = house_questions.match("ring Jaco's phone")
        self.assertEqual(request, ("phone", ("ring", "jaco")))
        answer = turn_http_entry._house_question(request, services, None)
        self.assertEqual(answer.outcome, Outcome.REQUESTED)


if __name__ == "__main__":
    unittest.main()
