"""Background routine response routing regression tests."""
import unittest
from unittest.mock import Mock
from declan.turn.response_composition import background_reply


class BackgroundReplyTests(unittest.TestCase):
    def setUp(self):
        self.personality = Mock()
        for name in ("morning_request_reply", "night_request_reply",
                     "sexy_request_reply", "movie_request_reply"):
            getattr(self.personality, name).return_value = name

    def reply(self, category, **options):
        selection = (("auto:script.test", {"_declan_background": True,
                     "_declan_reply_category": category, **options}), None)
        return background_reply("started", selection, guest=False,
                                visitor_present=False, personality=self.personality)

    def test_morning(self):
        self.assertEqual(self.reply("morning"), "morning_request_reply")
        self.personality.morning_request_reply.assert_called_once_with(guest=False, visitor_present=False)

    def test_night(self):
        self.assertEqual(self.reply("night"), "night_request_reply")

    def test_sexy_operation(self):
        self.assertEqual(self.reply("sexy", operation="end"), "sexy_request_reply")
        self.personality.sexy_request_reply.assert_called_once_with("end", guest=False, visitor_present=False)

    def test_movie_action(self):
        self.assertEqual(self.reply("movie", requested_action="open"), "movie_request_reply")
        self.personality.movie_request_reply.assert_called_once_with("open", guest=False, visitor_present=False)

    def test_non_started_or_chained_does_not_decorate(self):
        selection = (("auto:script.test", {"_declan_background": True}), "play country")
        self.assertIsNone(background_reply("started", selection, guest=False,
                                          visitor_present=False, personality=self.personality))
        self.assertIsNone(background_reply("confirmed", (selection[0], None), guest=False,
                                          visitor_present=False, personality=self.personality))
        self.personality.assert_not_called()
