"""FUT-27: shopping and to-do lists in Home Assistant's own to-do lists."""
import json
import unittest
from types import SimpleNamespace

from declan.core.execution_results import Outcome
from declan.ha import todo_lists
from declan.turn import turn_http_entry, whereabouts

# What HA sends back after a service call in a busy house: every state that changed meanwhile.
CHANGED = [{"entity_id": f"sensor.s{n}", "state": "x" * 300} for n in range(1000)]
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
        return json.dumps(self.body).encode()[:limit]  # like a real response: cut off at the limit


class Opener(FakeHA):
    def open(self, request, timeout=None):
        path = request.full_url.removeprefix("http://ha")
        data: dict = json.loads(request.data) if request.data else {}
        self.calls.append((path, data))
        if path == "/api/states":
            # A big house: far more than the 256 KB read limit.
            return Response(STATES + [{"entity_id": f"sensor.s{n}", "state": "x" * 300} for n in range(1000)])
        if path == "/api/template":
            assert "states.todo" in data["template"]
            return Response([row for row in STATES if str(row["entity_id"]).startswith("todo.")])
        if path.startswith("/api/services/todo/get_items"):
            entity = data["entity_id"]
            return Response({"changed_states": CHANGED, "service_response": {entity: {"items": [
                {"summary": item, "status": "needs_action"} for item in self.items[entity]]}}})
        if path == "/api/services/todo/add_item":
            self.items[data["entity_id"]].append(data["item"])
        elif path == "/api/services/todo/update_item":
            self.items[data["entity_id"]].remove(data["item"])
        else:
            return Response([])
        return Response(CHANGED)


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

    def test_polite_requests(self):
        # 27 Nov 2026: the satellite heard this and it went to the AI agent.
        self.assertEqual(todo_lists.match("Can you add shampoo and conditioner to our shopping list, please?"),
                         ("add", "shopping", ["shampoo", "conditioner"]))
        self.assertEqual(todo_lists.match("please put milk on the list thanks"), ("add", "shopping", ["milk"]))
        self.assertEqual(todo_lists.match("could you read me the shopping list"), ("read", "shopping", []))
        self.assertEqual(todo_lists.match("would you take eggs off the shopping list please")[0], "remove")
        opener = Opener()
        self.assertEqual(self.run_phrase("Can you add shampoo and conditioner to our shopping list, please?",
                                         opener).outcome, Outcome.CONFIRMED)
        self.assertIn("Conditioner", opener.items["todo.shopping_list"])

    def test_a_slow_add_that_landed_counts_as_added(self):
        # iCloud-synced lists can be slower than the timeout; HA still adds the item (27 Nov 2026).
        class Slow(Opener):
            def open(self, request, timeout=None):
                if request.full_url.endswith("/api/services/todo/add_item"):
                    assert timeout == todo_lists.WRITE_TIMEOUT
                    super().open(request, timeout)
                    raise TimeoutError("timed out")
                return super().open(request, timeout)
        opener = Slow()
        result = self.run_phrase("add milk to the shopping list", opener)
        self.assertEqual(result.outcome, Outcome.CONFIRMED)
        self.assertIn("Milk", opener.items["todo.shopping_list"])
        self.assertEqual(todo_lists.add_to_shopping(("http://ha", {}, Slow()), "eggs"), "added")

    def test_a_slow_add_that_didnt_land_is_still_a_failure(self):
        class Lost(Opener):
            def open(self, request, timeout=None):
                if request.full_url.endswith("/api/services/todo/add_item"):
                    raise TimeoutError("timed out")
                return super().open(request, timeout)
        self.assertEqual(self.run_phrase("add milk to the shopping list", Lost()).outcome, Outcome.UNAVAILABLE)

    def test_answered_in_the_request_flow(self):
        services = SimpleNamespace(ha_device_connection=lambda: ("http://ha", {}, Opener()))
        result = turn_http_entry._todo(todo_lists.match("add milk to the list"), services)
        self.assertEqual(result.outcome, Outcome.CONFIRMED)



class LargeHouseTests(unittest.TestCase):
    def test_lists_work_when_all_states_are_bigger_than_the_read_limit(self):
        # 26 Nov 2026: "add rice to the shopping list" said "I couldn't reach the shopping list"
        # because /api/states was cut off at 256 KB. Only the to-do lists are asked for now.
        opener = Opener()
        request = todo_lists.match("add rice to the shopping list")
        assert request is not None
        reply = todo_lists.result(request, ("http://ha", {}, opener)).reply
        self.assertTrue(reply.startswith("Added rice"), reply)
        self.assertNotIn("/api/states", [path for path, _ in opener.calls])
        self.assertEqual(todo_lists.add_to_shopping(("http://ha", {}, opener), "beans"), "added")



class CheckTests(unittest.TestCase):
    def ask(self, phrase, items):
        request = todo_lists.match(phrase)
        assert request is not None, phrase
        return todo_lists.result(request, ("http://ha", {}, Opener(items))).reply

    def test_is_it_on_the_list(self):
        self.assertEqual(self.ask("do I have rice on the shopping list?", ["Milk", "Rice"]),
                         "Yes, Rice is on the shopping list.")
        self.assertEqual(self.ask("is bread on the list", ["Milk"]), "No, bread isn't on the shopping list.")
        self.assertEqual(self.ask("are milk and eggs on the shopping list", ["Milk"]),
                         "Milk is on the shopping list, but not eggs.")
        self.assertEqual(self.ask("did someone add milk to the shopping list", ["Semi-skimmed milk"]),
                         "Yes, Semi-skimmed milk is on the shopping list.")
        self.assertEqual(todo_lists.match("is anything on the shopping list"), ("read", "shopping", []))


class ServiceReplyTests(unittest.TestCase):
    def test_a_huge_service_reply_isnt_a_failure(self):
        # 26 Nov 2026: milk was added, but the reply listed so many changed states
        # that it was cut off, and Declan said "I couldn't reach the shopping list".
        from declan.ha import ha_replies
        huge = json.dumps(CHANGED).encode()
        self.assertGreater(len(huge), 262144)

        class Body:
            def read(self, limit):
                return huge[:limit]
        self.assertEqual(ha_replies.decode(Body(), "/api/services/todo/add_item", 262144), [])
        self.assertEqual(ha_replies.decode(Body(), "/api/services/todo/get_items?return_response", 262144), CHANGED)
        self.assertEqual(ha_replies.decode(Body(), "/api/services/input_boolean/turn_on", 8192), [])
        with self.assertRaises(ValueError):
            ha_replies.decode(Body(), "/api/states", 262144)

    def test_every_service_caller_uses_it(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1] / "declan"
        for module in ("ha/todo_lists.py", "ha/intercom.py", "ha/ha_reads.py", "timers/timers.py",
                       "ha/household_routine_dispatch.py"):
            with self.subTest(module=module):
                self.assertIn("ha_replies.decode(response, path,", (root / module).read_text())


if __name__ == "__main__":
    unittest.main()
