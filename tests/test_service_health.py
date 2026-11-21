"""FUT-24: blame a service only after checking it's down."""
import json
import unittest
from email.message import Message
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

from declan.core.execution_results import Outcome
from declan.ha import service_health
from declan.turn import conversation_entry, turn_http_entry


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
    def __init__(self, api=None, players=("playing",), error=None):
        self.api, self.players, self.error, self.calls = api or {"message": "API running."}, list(players), error, 0

    def open(self, request, timeout=None):
        self.calls += 1
        if self.error:
            raise self.error
        return Response(self.players if request.full_url.endswith("/api/template") else self.api)


class HealthTests(unittest.TestCase):
    def setUp(self):
        service_health.clear_cache()

    def explain(self, reply, ha, now=0.0):
        return service_health.explain(reply, ("http://ha", {}, ha), now=now)

    def test_home_assistant_down_or_refusing_is_named(self):
        refused = URLError(ConnectionRefusedError(111, "Connection refused"))
        self.assertEqual(self.explain("I couldn't check the music players.", FakeHA(error=refused)), service_health.HA_DOWN)
        service_health.clear_cache()
        self.assertEqual(self.explain("x", FakeHA(error=TimeoutError())), service_health.HA_DOWN)
        service_health.clear_cache()
        rejected = HTTPError("u", 401, "no", Message(), None)
        self.assertEqual(self.explain("x", FakeHA(error=rejected)), service_health.HA_AUTH)

    def test_music_down_only_for_music_failures_and_only_when_every_player_is_unavailable(self):
        down = FakeHA(players=("unavailable", "unavailable"))
        self.assertEqual(self.explain("I couldn't reach Music Assistant.", down), service_health.MUSIC_DOWN)
        service_health.clear_cache()
        self.assertIsNone(self.explain("The kitchen light is unavailable.", down))
        service_health.clear_cache()
        self.assertIsNone(self.explain("I couldn't reach Music Assistant.", FakeHA(players=("unavailable", "idle"))))

    def test_nothing_is_blamed_when_the_check_cannot_run(self):
        self.assertIsNone(service_health.explain("x", None))
        self.assertIsNone(self.explain("x", FakeHA(error=URLError("Name or service not known"))))
        service_health.clear_cache()
        self.assertIsNone(self.explain("music failed", FakeHA(players=())))  # no MA players at all: unknown

    def test_checks_are_cached(self):
        ha = FakeHA(error=TimeoutError())
        for second in (0.0, 10.0, 29.0):
            self.explain("x", ha, now=second)
        self.assertEqual(ha.calls, 1)
        self.explain("x", ha, now=31.0)
        self.assertEqual(ha.calls, 2)

    def test_request_flow_keeps_successes_and_replaces_failures(self):
        services = SimpleNamespace(ha_device_connection=lambda: ("http://ha", {}, FakeHA(error=TimeoutError())))
        ok = conversation_entry._result_factory("Lights on.", Outcome.CONFIRMED)
        self.assertIs(turn_http_entry._explain_failure(ok, services), ok)
        failed = conversation_entry._result_factory("I couldn't reach the lights.", Outcome.UNAVAILABLE)
        result = turn_http_entry._explain_failure(failed, services)
        self.assertEqual((result.reply, result.outcome), (service_health.HA_DOWN, Outcome.UNAVAILABLE))
        self.assertIsNone(turn_http_entry._explain_failure(None, services))


if __name__ == "__main__":
    unittest.main()
