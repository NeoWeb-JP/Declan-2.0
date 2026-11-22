"""FUT-30: who's home, from Home Assistant person entities."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from declan.core.execution_results import Outcome
from declan.ha import presence
from declan.turn import house_questions, turn_http_entry

PEOPLE = [["person.jaco", "home", "Jaco"], ["person.edd", "work", "Edd"]]


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
    def __init__(self, rows=None, fail=False):
        self.rows = PEOPLE if rows is None else rows
        self.fail = fail
        self.calls = []

    def open(self, request, timeout=None):
        self.calls.append(request.full_url)
        if self.fail:
            raise OSError("offline")
        return Response(self.rows)


def ask(phrase, rows=None, guest=False, fail=False):
    ha = FakeHA(rows, fail)
    return presence.result(presence.match(phrase), ("http://ha", {}, ha), guest=guest), ha


class MatchTests(unittest.TestCase):
    def test_phrases(self):
        cases = {
            "Is Edd home?": ("one", "edd"), "is jaco back yet": ("one", "jaco"), "has Edd left": ("one", "edd"),
            "did Edd get home": ("one", "edd"), "Declan, is Edd in?": ("one", "edd"),
            "who's home": ("all",), "who is in": ("all",), "who's at home right now": ("all",),
            "is everyone home": ("all",), "is anyone home": ("anyone",), "is anybody in": ("anyone",),
            "is the house empty": ("anyone",),
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(presence.match(phrase), expected)

    def test_not_presence(self):
        for phrase in ("turn on the lights", "is the light on", "is it on", "where's my phone", "who are you", None):
            with self.subTest(phrase=phrase):
                self.assertIsNone(presence.match(phrase))


class ResultTests(unittest.TestCase):
    def test_one_person_home_or_out_never_says_the_zone(self):
        result, _ = ask("is Jaco home")
        self.assertEqual((result.reply, result.outcome), ("Yes, Jaco's home.", Outcome.CHAT_ANSWER))
        result, _ = ask("is Edd home")
        self.assertEqual(result.reply, "No, Edd's out.")
        self.assertNotIn("work", result.reply)

    def test_full_name_first_name_and_entity_id(self):
        rows = [["person.edward_smith", "home", "Edward Smith"]]
        for phrase in ("is Edward home", "is Edward Smith home", "is edward smith in"):
            with self.subTest(phrase=phrase):
                self.assertEqual(ask(phrase, rows)[0].reply, "Yes, Edward Smith's home.")

    def test_unknown_state_is_not_guessed(self):
        result, _ = ask("is Edd home", [["person.edd", "unknown", "Edd"]])
        self.assertEqual(result.outcome, Outcome.UNAVAILABLE)
        self.assertIn("can't tell", result.reply)

    def test_not_a_person_lets_declan_answer(self):
        self.assertIsNone(ask("is the washing in")[0])

    def test_who_is_home(self):
        self.assertEqual(ask("who's home")[0].reply, "Just Jaco.")
        self.assertEqual(ask("who's home", [["person.a", "home", "Jaco"], ["person.b", "home", "Edd"]])[0].reply,
                         "Everyone's home.")
        self.assertEqual(ask("who's home", [["person.a", "away", "Jaco"], ["person.b", "not_home", "Edd"]])[0].reply,
                         "Nobody's home. Just me, talking to myself.")
        three = [["person.a", "home", "Jaco"], ["person.b", "home", "Edd"], ["person.c", "unavailable", "Gran"]]
        self.assertEqual(ask("who's in", three)[0].reply, "Jaco and Edd are home. I can't tell about Gran.")

    def test_anyone_home(self):
        self.assertEqual(ask("is anyone home")[0].reply, "Yes: Jaco.")
        self.assertEqual(ask("is anyone home", [["person.a", "away", "Jaco"]])[0].reply, "No, nobody's home.")

    def test_no_people_configured(self):
        self.assertEqual(ask("who's home", [])[0].outcome, Outcome.NOT_CONFIGURED)

    def test_refused_in_guest_mode_without_asking_home_assistant(self):
        with patch("declan.turn.line_freshness.pick", side_effect=lambda key, lines, **_: lines[0]):
            result, ha = ask("is Edd home", guest=True)
        self.assertEqual(result.outcome, Outcome.REJECTED)
        self.assertIn(result.reply, presence.GUEST_LINES)
        self.assertNotIn("Edd", result.reply)
        self.assertEqual(ha.calls, [])

    def test_home_assistant_down(self):
        result, _ = ask("who's home", fail=True)
        self.assertEqual(result.outcome, Outcome.UNAVAILABLE)
        result = presence.result(("all",), None, guest=False)
        self.assertEqual(result.outcome, Outcome.NOT_CONFIGURED)


class RouterTests(unittest.TestCase):
    def services(self, guest="off", ha=None):
        ha = ha or FakeHA()
        return SimpleNamespace(read_guest_mode=lambda: guest, ha_device_connection=lambda: ("http://ha", {}, ha))

    def test_router_and_turn_entry(self):
        request = house_questions.match("is Jaco home")
        self.assertEqual(request, ("presence", ("one", "jaco")))
        answer = turn_http_entry._house_question(request, self.services(), "sat")
        self.assertEqual(answer.reply, "Yes, Jaco's home.")

    def test_unreadable_guest_mode_counts_as_guest(self):
        def broken():
            raise OSError("no")
        services = SimpleNamespace(read_guest_mode=broken, ha_device_connection=lambda: ("http://ha", {}, FakeHA()))
        with patch("declan.turn.line_freshness.pick", side_effect=lambda key, lines, **_: lines[0]):
            answer = turn_http_entry._house_question(("presence", ("all",)), services, None)
        self.assertEqual(answer.outcome, Outcome.REJECTED)

    def test_not_a_person_falls_through(self):
        self.assertIsNone(turn_http_entry._house_question(("presence", ("one", "washing")), self.services(), None))


if __name__ == "__main__":
    unittest.main()
