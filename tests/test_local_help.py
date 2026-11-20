"""Free local help: what can you do, lights in here, routines, rooms, speakers."""
import unittest

from declan.turn import local_help

ROWS = [
    {"entity_id": "light.kitchen_spots", "declan_area": "Kitchen", "attributes": {"friendly_name": "Kitchen Spots"}},
    {"entity_id": "light.kitchen_pendant", "declan_area": "Kitchen", "attributes": {"friendly_name": "Kitchen Pendant"}},
    {"entity_id": "cover.kitchen_blind", "declan_area": "Kitchen", "attributes": {"friendly_name": "Kitchen Blind"}},
    {"entity_id": "media_player.kitchen", "declan_area": "Kitchen", "attributes": {"friendly_name": "Kitchen Speaker"}},
    {"entity_id": "light.office", "declan_area": "Office", "attributes": {"friendly_name": "Office"}},
]
CONTEXT = {"you_are_in": "Kitchen", "areas": {"Kitchen", "Office"},
           "music_rooms": {"kitchen", "lounge", "everywhere", "upstairs", "downstairs"},
           "routines": {"good night", "movie time", "good morning", "dinner"}}


class LocalHelpTests(unittest.TestCase):
    def ask(self, phrase, *, context=CONTEXT, conversation_on=True):
        request = local_help.match(phrase)
        self.assertIsNotNone(request, phrase)
        return local_help.answer(request, rows=ROWS, context=context, conversation_on=conversation_on)

    def test_matching(self):
        for phrase in ("What can you do?", "help", "Declan, what can I say", "which lights are in here",
                       "what lights are in the office", "what devices are in this room", "what routines are there",
                       "list the routines", "what rooms do you know", "where can you play music"):
            with self.subTest(phrase=phrase):
                self.assertIsNotNone(local_help.match(phrase))
        for phrase in ("turn on the lights", "what lights are on", "help me find my keys", "play music"):
            with self.subTest(phrase=phrase):
                self.assertIsNone(local_help.match(phrase))

    def test_help_mentions_real_rooms_and_routines(self):
        reply = self.ask("what can you do")
        self.assertIn("kitchen and lounge or everywhere", reply)
        self.assertIn("dinner, good morning and good night", reply)
        self.assertTrue(reply.endswith("in your own words."))
        self.assertIn("Try", self.ask("help", conversation_on=False))

    def test_lights_here_and_named_room(self):
        self.assertEqual(self.ask("which lights are in here"), "In here: Kitchen Blind, Kitchen Pendant and Kitchen Spots.")
        self.assertEqual(self.ask("what lights are in the office"), "In the office: Office.")
        self.assertIn("can't see", self.ask("what lights are in the garage"))
        self.assertIn("Which room", self.ask("which lights are in here", context=dict(CONTEXT, you_are_in=None)))

    def test_routines_rooms_speakers(self):
        self.assertEqual(self.ask("what routines are there"), "I can run dinner, good morning, good night and movie time.")
        self.assertEqual(self.ask("what rooms do you know"), "I know these rooms: Kitchen and Office.")
        self.assertEqual(self.ask("where can you play music"), "I can play music in the kitchen and lounge, or everywhere.")
        empty = dict(CONTEXT, routines=set(), music_rooms={"everywhere"}, areas=set())
        self.assertIn("can't see any routines", self.ask("list the routines", context=empty))
        self.assertIn("No music speakers", self.ask("where can you play music", context=empty))


if __name__ == "__main__":
    unittest.main()
