import io
import json
import os
import unittest
from unittest.mock import patch

from openai_planner import request_plan
from model_response_results import ModelResponseResult, ModelResponseStatus


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.request = None

    def open(self, request, timeout):
        self.request = request
        return io.BytesIO(json.dumps(self.response).encode())


def response(plan):
    return {"status": "completed", "output": [
        {"type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": json.dumps(plan)}
        ]}
    ]}


class OpenAIPlannerTests(unittest.TestCase):
    def test_response_result_is_typed_frozen_and_not_an_execution_result(self):
        result = ModelResponseResult.parse(response({"actions": []}))
        self.assertIs(result.status, ModelResponseStatus.COMPLETED)
        self.assertEqual(json.loads(result.text), {"actions": []})
        with self.assertRaises(AttributeError):
            setattr(result, "text", "changed")
        for status in ("incomplete", "failed", "cancelled", "in_progress", "queued", "COMPLETED", None, [], {}):
            with self.subTest(status=status):
                parsed = ModelResponseResult.parse({"status": status, "output": "ignored"})
                self.assertIs(parsed.status, ModelResponseStatus.UNVERIFIED)
                self.assertIsNone(parsed.text)

    def test_invalid_provider_results_still_account_usage_before_rejection(self):
        valid = response({"actions": []})
        message = valid["output"][0]
        cases = [{"status": status, "output": valid["output"]}
                 for status in ("incomplete", "future", "COMPLETED", [], None)]
        cases.extend({"status": "completed", "output": output} for output in
                     ([], [message, message], [None], [{**message, "content": None}],
                      [{**message, "content": [{"type": "output_text", "text": []}]}]))
        for payload in cases:
            with self.subTest(payload=payload):
                payload["usage"] = {"input_tokens": 10, "output_tokens": 2}
                usage = []
                with self.assertRaisesRegex(ValueError, "^Invalid model plan$"):
                    request_plan("lights on", ["light.kitchen"], opener=FakeOpener(payload),
                                 model="gpt-5-mini", api_key="test", usage_sink=usage.append)
                self.assertEqual(usage, [payload["usage"]])

    def test_validated_candidate_no_dispatch(self):
        opener = FakeOpener(response({"actions": [{"entity_id": "light.kitchen", "service": "turn_on"}]}))
        plan = request_plan("lights on", ["light.kitchen"], opener=opener, model="gpt-5-mini", api_key="test")
        self.assertEqual(plan[0].entity_id, "light.kitchen")
        body = json.loads(opener.request.data)
        self.assertFalse(body["store"])
        self.assertEqual(body["max_output_tokens"], 600)

    def test_unexposed_rejected(self):
        opener = FakeOpener(response({"actions": [{"entity_id": "light.private", "service": "turn_on"}]}))
        with self.assertRaises(ValueError):
            request_plan("lights on", ["light.kitchen"], opener=opener, model="gpt-5-mini", api_key="test")

    def test_empty_plan_means_no_action(self):
        opener = FakeOpener(response({"actions": []}))
        self.assertEqual(request_plan("?", [], opener=opener, model="gpt-5-mini", api_key="test"), ())

    def test_usage_and_safe_context(self):
        data = response({"actions": []})
        data["usage"] = {"input_tokens": 120, "output_tokens": 35}
        opener = FakeOpener(data)
        captured = []
        request_plan("turn on kitchen", ["light.kitchen"], opener=opener,
                     model="gpt-5-mini", api_key="test",
                     usage_sink=captured.append,
                     inventory=[{"entity_id": "light.kitchen", "state": "off",
                                 "attributes": {"friendly_name": "Kitchen"}}])
        self.assertEqual(captured, [{"input_tokens": 120, "output_tokens": 35}])
        body = json.loads(opener.request.data)
        context = json.loads(body["input"])["current_state"]
        self.assertEqual(context[0]["name"], "Kitchen")

    def test_context_cannot_inject_other_entity(self):
        with self.assertRaises(ValueError):
            request_plan("turn on kitchen", ["light.kitchen"], model="gpt-5-mini",
                         api_key="test", inventory=[{"entity_id": "light.private",
                                                    "state": "off", "attributes": {}}])

    def test_cost_ceiling_blocks_api_request(self):
        opener = FakeOpener(response({"actions": []}))
        with self.assertRaises(ValueError):
            request_plan("turn on kitchen", ["light.kitchen"], opener=opener,
                         model="gpt-5-mini", api_key="test",
                         max_cost_micro_usd=1)
        self.assertIsNone(opener.request)

    def test_environment_model_and_key_are_used_when_not_explicitly_passed(self):
        opener = FakeOpener(response({"actions": []}))
        with patch.dict(os.environ, {"DECLAN_OPENAI_MODEL": "gpt-5-mini",
                                     "OPENAI_API_KEY": "environment-test-key"}):
            self.assertEqual(request_plan("lights on", [], opener=opener), ())
        self.assertEqual(json.loads(opener.request.data)["model"], "gpt-5-mini")
        self.assertEqual(opener.request.get_header("Authorization"), "Bearer environment-test-key")

    def test_explicit_model_and_key_override_environment(self):
        opener = FakeOpener(response({"actions": []}))
        with patch.dict(os.environ, {"DECLAN_OPENAI_MODEL": "invalid model",
                                     "OPENAI_API_KEY": ""}):
            self.assertEqual(request_plan("lights on", [], opener=opener,
                                          model="gpt-5-mini", api_key="explicit-key"), ())
        self.assertEqual(json.loads(opener.request.data)["model"], "gpt-5-mini")
        self.assertEqual(opener.request.get_header("Authorization"), "Bearer explicit-key")

    def test_unset_environment_configuration_fails_before_network(self):
        opener = FakeOpener(response({"actions": []}))
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "Configure a supported OpenAI model"):
                request_plan("lights on", [], opener=opener)
        self.assertIsNone(opener.request)

    def test_missing_credentials_fail_closed(self):
        with self.assertRaises(ValueError):
            request_plan("lights on", ["light.kitchen"], model="gpt-5-mini", api_key="")

    def test_incomplete_response_rejected(self):
        opener = FakeOpener({"status": "incomplete", "output": []})
        with self.assertRaises(ValueError):
            request_plan("lights on", ["light.kitchen"], opener=opener, model="gpt-5-mini", api_key="test")


if __name__ == "__main__":
    unittest.main()
