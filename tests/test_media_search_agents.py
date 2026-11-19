"""Independent Home Assistant media-search provider selection and loop safety."""

import json
import unittest
from unittest.mock import Mock

from declan.music import media_search_agents as agents


class Response:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.body


class FakeOpener:
    def __init__(self, *, legacy=(), self_agents=(), states=None, unavailable=False):
        self.legacy = list(legacy)
        self.self_agents = list(self_agents)
        self.states = states or {}
        self.unavailable = unavailable
        self.calls = []

    def open(self, request, timeout=0):
        self.calls.append(request.full_url)
        if self.unavailable:
            raise OSError("HA unreachable")
        if request.full_url.endswith("/api/template"):
            return Response({"legacy": self.legacy, "self": self.self_agents})
        prefix = "http://ha/api/states/"
        if request.full_url.startswith(prefix):
            return Response(self.states.get(request.full_url[len(prefix):], {}))
        raise AssertionError("Unexpected HTTP request: " + request.full_url)


class MediaSearchAgentTests(unittest.TestCase):
    def connection(self, opener):
        return ("http://ha", {"Authorization": "Bearer test"}, opener)

    def test_default_legacy_discovery_still_works(self):
        opener = FakeOpener(legacy=["conversation.jarvis_local"])
        self.assertEqual(agents.resolve(self.connection(opener), ""),
                         "conversation.jarvis_local")
        self.assertEqual(len(opener.calls), 1)

    def test_explicit_nonlegacy_provider_is_supported_after_state_verification(self):
        name = "conversation.separate_media_provider"
        opener = FakeOpener(states={name: {"entity_id": name, "state": "idle"}})
        self.assertEqual(agents.resolve(self.connection(opener), name), name)
        self.assertEqual(len(opener.calls), 2)

    def test_registered_conversation_agent_can_have_unknown_state(self):
        name = "conversation.media_provider"
        opener = FakeOpener(states={name: {"entity_id": name, "state": "unknown"}})
        self.assertEqual(agents.resolve(self.connection(opener), name), name)

    def test_self_agent_is_rejected_without_attempting_conversation_call(self):
        name = "conversation.declan_2_0"
        opener = FakeOpener(self_agents=[name], states={
            name: {"entity_id": name, "state": "idle"}})
        with self.assertRaisesRegex(agents.MediaAgentError, "own conversation agent"):
            agents.resolve(self.connection(opener), name)
        self.assertEqual(len(opener.calls), 1)

    def test_self_agents_are_not_auto_selected_even_when_legacy_list_contains_them(self):
        name = "conversation.declan_2_0"
        opener = FakeOpener(legacy=[name], self_agents=[name])
        with self.assertRaisesRegex(agents.MediaAgentError, "No independent"):
            agents.resolve(self.connection(opener), "")

    def test_ambiguous_legacy_discovery_requires_explicit_choice(self):
        opener = FakeOpener(legacy=["conversation.jarvis_local", "conversation.declan_local"])
        with self.assertRaisesRegex(agents.MediaAgentError, "Multiple"):
            agents.resolve(self.connection(opener), "")

    def test_explicit_provider_must_be_available_and_match_exact_id(self):
        name = "conversation.media"
        for value in ({}, {"entity_id": name, "state": "unavailable"},
                      {"entity_id": "conversation.other", "state": "idle"}):
            with self.subTest(value=value):
                opener = FakeOpener(states={name: value})
                with self.assertRaises(agents.MediaAgentError):
                    agents.resolve(self.connection(opener), name)

    def test_invalid_provider_rejected_without_network(self):
        opener = Mock()
        with self.assertRaises(agents.MediaAgentError):
            agents.resolve(self.connection(opener), "sensor.other")
        opener.open.assert_not_called()

    def test_unavailable_ha_returns_distinct_error(self):
        opener = FakeOpener(unavailable=True)
        with self.assertRaises(agents.MediaAgentUnavailable):
            agents.resolve(self.connection(opener), "")


if __name__ == "__main__":
    unittest.main()
