"""FUT-76: pantry by voice. Local stock, minimums, and low or finished items go on the shopping list."""
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from declan.core.execution_results import Outcome
from declan.ha import todo_lists
from declan.turn import household_settings, line_freshness, pantry, turn_http_entry, whereabouts


class Store(unittest.TestCase):
    def setUp(self):
        folder = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(pantry, "PATH", folder / "pantry.sqlite3"))
        self.enterContext(patch.object(line_freshness, "PATH", folder / "fresh.sqlite3"))
        self.enterContext(patch.object(line_freshness, "_start_top_up", Mock()))
        self.enterContext(patch.object(household_settings, "PATH", folder / "household.json"))
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.listed = []
        self.list_works = True

    def add_to_list(self, item):
        if not self.list_works:
            return "unavailable"
        if item in self.listed:
            return "already"
        self.listed.append(item)
        return "added"

    def say(self, text, *, guest=False):
        request = pantry.match(text)
        assert request is not None, text
        return pantry.answer(request, guest=guest, add_to_list=self.add_to_list)


class MatchTests(unittest.TestCase):
    def test_everyday_phrases(self):
        cases = {
            "we've got 6 tins of chopped tomatoes": ("stock", ("chopped tomatoes", 6, "tin")),
            "Declan, we have 2 loaves of bread": ("stock", ("bread", 2, "loaf")),
            "we have 12 eggs left": ("stock", ("eggs", 12, None)),
            "I bought 2 bags of rice": ("add", ("rice", 2, "bag")),
            "I put 6 tins of beans in the pantry": ("add", ("beans", 6, "tin")),
            "I've used a tin of chopped tomatoes": ("used", ("chopped tomatoes", 1, "tin")),
            "used 2 tins of tomatoes": ("used", ("tomatoes", 2, "tin")),
            "I've used the last tin of tomatoes": ("used", ("tomatoes", None, "tin")),
            "used up the rice": ("used", ("rice", None, None)),
            "finished the milk": ("used", ("milk", None, None)),
            "we're out of rice": ("out", "rice"),
            "we've run out of toilet roll": ("out", "toilet roll"),
            "there's no milk left": ("out", "milk"),
            "we're running low on coffee": ("low", "coffee"),
            "do we have pasta?": ("have", "pasta"),
            "how many tins of tomatoes have we got?": ("count", "tomatoes"),
            "keep at least 4 tins of tomatoes": ("minimum", ("tomatoes", 4, "tin")),
            "the minimum for coffee is 2": ("minimum", ("coffee", 2, None)),
            "what's running low?": ("list", None),
            "stop counting rice": ("forget", "rice"),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(pantry.match(text), expected)

    def test_chatter_and_other_features_are_left_alone(self):
        for text in ("we've got 3 guests", "we've got 10 minutes", "i had a beer", "ran out of time",
                     "add milk to the shopping list", "have we got any guests", "turn on the lights",
                     "the spare key is in the hall drawer"):
            with self.subTest(text=text):
                self.assertIsNone(pantry.match(text))


class AnswerTests(Store):
    def test_count_use_and_restock(self):
        self.assertIn("6 tins of chopped tomatoes", self.say("we've got 6 tins of chopped tomatoes"))
        self.assertIn("5 tins of chopped tomatoes left", self.say("I've used a tin of tomatoes"))
        self.assertIn("8 tins of chopped tomatoes", self.say("I bought 3 tins of chopped tomatoes"))
        self.assertEqual(self.say("how many tins of tomatoes have we got"), "8 tins of chopped tomatoes left.")
        self.assertEqual(self.say("do we have chopped tomatoes"), "8 tins of chopped tomatoes, yes.")
        self.assertEqual(self.listed, [])

    def test_below_the_minimum_goes_on_the_shopping_list_once(self):
        self.say("we've got 5 tins of tomatoes")
        self.say("keep at least 4 tins of tomatoes")
        self.say("used a tin of tomatoes")
        reply = self.say("used a tin of tomatoes")
        self.assertIn("3 tins of tomatoes left", reply)
        self.assertIn("on the shopping list", reply)
        self.assertIn("already on the shopping list", self.say("used a tin of tomatoes"))
        self.assertEqual(self.listed, ["Tomatoes"])
        self.assertIn("tomatoes (2)", self.say("what's running low"))

    def test_the_last_one_and_running_out(self):
        self.say("we've got 2 bags of rice")
        reply = self.say("used the last bag of rice")
        self.assertIn("last of the rice", reply)
        self.assertEqual(self.say("do we have rice"), "No rice left, my bru.")
        self.assertIn("on the shopping list", self.say("we're out of coffee"))
        self.assertIn("on the shopping list", self.say("we're running low on milk"))
        self.assertEqual(self.listed, ["Rice", "Coffee", "Milk"])

    def test_joke_first_then_the_answer(self):
        reply = self.say("we've got 6 tins of beans")
        self.assertTrue(reply.endswith("6 tins of beans."), reply)
        self.assertGreater(len(reply), len("6 tins of beans."))

    def test_unknown_items(self):
        self.assertIn("wasn't counting beans", self.say("used a tin of beans"))
        self.assertIn("not counting beans", self.say("how many tins of beans have we got"))
        self.assertIsNone(self.say("do we have beans"))  # let the rest of Declan answer
        self.assertIn("not counting anything", self.say("what's running low"))

    def test_shopping_list_failure_is_said(self):
        self.list_works = False
        self.assertIn("couldn't get it onto the shopping list", self.say("we're out of salt"))

    def test_guests_can_use_but_not_change_counts(self):
        self.say("we've got 4 tins of beans")
        self.assertIn("Only the household", self.say("we've got 9 tins of beans", guest=True))
        self.assertIn("Only the household", self.say("keep at least 9 tins of beans", guest=True))
        self.assertIn("3 tins of beans left", self.say("used a tin of beans", guest=True))
        self.assertIn("shopping list", self.say("we're out of milk", guest=True))

    def test_forget_and_listing(self):
        self.say("we've got 3 jars of jam")
        self.assertEqual(pantry.listing()[0] | {"updated_at": 0},
                         {"item": "jam", "unit": "jar", "count": 3, "minimum": 0, "updated_at": 0})
        self.assertEqual(self.say("stop counting jam"), "I've stopped counting jam.")
        self.assertEqual(pantry.listing(), [])


class ShoppingListTests(Store):
    def connection(self, items=(), lists=("todo.shopping_list",)):
        calls = []

        def call(connection, path, data=None):
            calls.append((path, data))
            if path == "/api/template":
                return [{"entity_id": entity, "state": "1", "attributes": {}} for entity in lists]
            if path.startswith("/api/services/todo/get_items"):
                return {"service_response": {data["entity_id"]: {"items": [{"summary": item} for item in items]}}}
            return []
        return calls, call

    def test_adds_once(self):
        calls, call = self.connection(items=["Milk"])
        with patch.object(todo_lists, "_call", side_effect=call):
            self.assertEqual(todo_lists.add_to_shopping(("http://ha", {}, None), "milk"), "already")
            self.assertEqual(todo_lists.add_to_shopping(("http://ha", {}, None), "Rice"), "added")
        self.assertIn(("/api/services/todo/add_item", {"entity_id": "todo.shopping_list", "item": "Rice"}), calls)

    def test_the_list_chosen_in_settings_wins(self):
        household_settings.save({"guest_tone": "home", "shopping_list": "todo.family"})
        calls, call = self.connection(lists=("todo.shopping_list", "todo.family"))
        with patch.object(todo_lists, "_call", side_effect=call):
            self.assertEqual(todo_lists.add_to_shopping(("http://ha", {}, None), "Rice"), "added")
        self.assertIn(("/api/services/todo/add_item", {"entity_id": "todo.family", "item": "Rice"}), calls)

    def test_a_missing_chosen_list_is_unavailable(self):
        household_settings.save({"guest_tone": "home", "shopping_list": "todo.gone"})
        _, call = self.connection()
        with patch.object(todo_lists, "_call", side_effect=call):
            self.assertEqual(todo_lists.add_to_shopping(("http://ha", {}, None), "Rice"), "unavailable")
        self.assertEqual(todo_lists.add_to_shopping(None, "Rice"), "unavailable")

    def test_setting_is_validated(self):
        with self.assertRaises(ValueError):
            household_settings.save({"guest_tone": "home", "shopping_list": "light.kitchen"})
        self.assertEqual(household_settings.listing()["settings"]["shopping_list"], "")


class TurnTests(Store):
    def test_answered_locally_and_unknown_guest_mode_cant_change_stock(self):
        services = SimpleNamespace(read_guest_mode=lambda: "off", ha_device_connection=lambda: None)
        result = turn_http_entry._pantry(pantry.match("we've got 6 tins of beans"), services)
        self.assertIs(result.outcome, Outcome.CONFIRMED)
        broken = SimpleNamespace(read_guest_mode=Mock(side_effect=OSError), ha_device_connection=lambda: None)
        refused = turn_http_entry._pantry(pantry.match("we've got 9 tins of beans"), broken)
        self.assertIn("Only the household", refused.reply)
        self.assertIsNone(turn_http_entry._pantry(pantry.match("do we have pasta"), services))

    def test_pantry_wins_over_where_did_i_put(self):
        self.assertIsNotNone(whereabouts.match("I put the beans in the pantry"))  # no count: still whereabouts
        self.assertIsNone(pantry.match("I put the beans in the pantry"))
        self.assertEqual(pantry.match("I put 6 tins of beans in the pantry")[0], "add")


class IntegrationViewTests(unittest.TestCase):
    def test_settings_and_pantry_listing_are_validated(self):
        from test_household_settings import load_view
        module, _ = load_view()
        base = {"guest_tone": "home", "shelve_days": 3, "fresh_lines": True, "christmas": "auto",
                "wifi_name": "", "wifi_password": ""}
        self.assertTrue(module.valid_settings(base))  # an older backend without the shopping list
        self.assertTrue(module.valid_settings({**base, "shopping_list": "todo.family"}))
        self.assertTrue(module.valid_settings({**base, "shopping_list": ""}))
        self.assertFalse(module.valid_settings({**base, "shopping_list": "light.kitchen"}))
        row = {"item": "beans", "unit": "tin", "count": 3, "minimum": 2, "updated_at": 1.0}
        self.assertTrue(module.valid_pantry(None))
        self.assertTrue(module.valid_pantry([row]))
        self.assertFalse(module.valid_pantry([{**row, "count": "3"}]))

    def test_panel_is_wired(self):
        js = (Path(__file__).resolve().parents[1] / "custom_components/declan_two/frontend/panel.js").read_text()
        for needle in ('name="shopping_list"', "renderPantry(response.pantry)", 'class="fresh-lines-list pantry-list"',
                       "shopping_list: shoppingList"):
            self.assertIn(needle, js)
