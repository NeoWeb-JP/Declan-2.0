"""FUT-27: shopping and to-do lists in Home Assistant's own to-do lists."""
import json
import unittest
from types import SimpleNamespace

from declan.core.execution_results import Outcome
from declan.ha import todo_lists
from declan.turn import turn_http_entry, whereabouts

STATES = [
    {"entity_id": "todo.shopping_list", "state": "2", "attributes": {"friendly_name": "Shopping List"}},
    {"entity_id": "todo.house_jobs", "state": "1", "attributes": {"friendly_name": "To-do"}},
    {"entity_id": "light.kitchen", "state": "on", "attributes": {}},
]


class FakeHA:
    def __init__(self, items=None):
        self.items = {"todo.shopping_list": list(items or []), "todo.house_jobs": ["Call the plumber"]}
        self.calls: list = []


class Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return json.dumps(self.body).encode()


class Opener(FakeHA):
    def open(self, request, timeout=None):
        path = request.full_url.removeprefix("http://ha")
        data: dict = json.loads(request.data) if request.data else {}
        self.calls.append((path, data))
        if path == "/api/states":
            return Response(STATES)
        if path.startswith("/api/services/todo/get_items"):
            entity = data["entity_id"]
            return Response({"service_response": {entity: {"items": [
                {"summary": item, "status": "needs_action"} for item in self.items[entity]]}}})
        if path == "/api/services/todo/add_item":
            self.items[data["entity_id"]].append(data["item"])
        elif path == "/api/services/todo/update_item":
            self.items[data["entity_id"]].remove(data["item"])
        return Response([])


class ListTests(unittest.TestCase):
    def run_phrase(self, phrase, opener):
        request = todo_lists.match(phrase)
        assert request is not None, phrase
        return todo_lists.result(request, ("http://ha", {}, opener))

    def test_phrases(self):
        cases = {"add milk and eggs to the shopping list": ("add", "shopping", ["milk", "eggs"]),
                 "put some bread on the list": ("add", "shopping", ["bread"]),
                 "i put milk on the shopping list": ("add", "shopping", ["milk"]),
                 "add call the plumber to my to-do list": ("add", "todo", ["call the plumber"]),
                 "what's on the shopping list": ("read", "shopping", []), "what do we need": ("read", "shopping", []),
                 "read me the to do list": ("read", "todo", []),
                 "take milk off the list": ("remove", "shopping", ["milk"]), "tick off eggs": ("remove", "shopping", ["eggs"])}
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(todo_lists.match(phrase), expected)
        for phrase in ("play jazz", "remove the kitchen light", "turn on the list lights please now"):
            self.assertIsNone(todo_lists.match(phrase))
        self.assertIsNone(whereabouts.match("i put milk on the shopping list"))

    def test_add_read_and_tick_off(self):
        opener = Opener()
        result = self.run_phrase("add milk and eggs to the shopping list", opener)
        self.assertEqual((result.reply, result.outcome), ("Added milk and eggs to the shopping list.", Outcome.CONFIRMED))
        self.assertEqual(opener.items["todo.shopping_list"], ["Milk", "Eggs"])
        self.assertEqual(self.run_phrase("what's on the shopping list", opener).reply,
                         "2 things on the shopping list: Milk and Eggs.")
        ticked = self.run_phrase("take milk and cheese off the list", opener)
        self.assertEqual((ticked.reply, ticked.outcome),
                         ("Ticked Milk off the shopping list. Cheese wasn't on it.", Outcome.PARTIAL))
        self.assertEqual(self.run_phrase("read me the to do list", opener).reply,
                         "One thing on the to-do list: Call the plumber.")

    def test_long_lists_are_summarised_and_empty_lists_said(self):
        opener = Opener(items=[f"Item {n}" for n in range(9)])
        self.assertTrue(self.run_phrase("what do we need", opener).reply.endswith("Item 5, and 3 more."))
        self.assertIn("is empty", self.run_phrase("what do we need", Opener()).reply)

    def test_missing_list_and_failures(self):
        global STATES
        saved, STATES = STATES, [row for row in STATES if "shopping" not in row["entity_id"]]
        try:
            self.assertEqual(self.run_phrase("add milk to the list", Opener()).outcome, Outcome.NOT_CONFIGURED)
        finally:
            STATES = saved

        class Broken:
            def open(self, request, timeout=None):
                raise OSError("down")
        self.assertEqual(self.run_phrase("add milk to the list", Broken()).outcome, Outcome.UNAVAILABLE)
        self.assertEqual(todo_lists.result(("read", "shopping", []), None).outcome, Outcome.NOT_CONFIGURED)

    def test_answered_in_the_request_flow(self):
        services = SimpleNamespace(ha_device_connection=lambda: ("http://ha", {}, Opener()))
        result = turn_http_entry._todo(todo_lists.match("add milk to the list"), services)
        self.assertEqual(result.outcome, Outcome.CONFIRMED)


if __name__ == "__main__":
    unittest.main()
