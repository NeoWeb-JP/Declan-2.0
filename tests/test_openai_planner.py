import io
import json
import unittest

from openai_planner import request_plan


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

    def test_missing_credentials_fail_closed(self):
        with self.assertRaises(ValueError):
            request_plan("lights on", ["light.kitchen"], model="gpt-5-mini", api_key="")

    def test_incomplete_response_rejected(self):
        opener = FakeOpener({"status": "incomplete", "output": []})
        with self.assertRaises(ValueError):
            request_plan("lights on", ["light.kitchen"], opener=opener, model="gpt-5-mini", api_key="test")


if __name__ == "__main__":
    unittest.main()
