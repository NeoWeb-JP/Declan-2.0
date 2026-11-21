"""FUT-60: Guest Mode makes Declan easy for people who have never used him."""
import unittest
from unittest.mock import Mock, patch

from declan.music import music
from declan.turn import local_help, session_turn_state, turn_response_composition
from declan.turn.command_vocabulary import GUEST_HINT, UNMATCHED_REPLY

PLAYLIST = "spotify://playlist/" + "a" * 22


class GenericMusicTests(unittest.TestCase):
    def test_vague_requests_pick_something_good(self):
        for phrase, room in (("play some music", None), ("put some music on", None), ("put on some music", None),
                             ("put some music on in the kitchen", "kitchen"), ("chuck some tunes on everywhere", "everywhere"),
                             ("music please", None), ("play something", None), ("play anything", None)):
            with self.subTest(phrase=phrase):
                self.assertEqual(music.parse(phrase), (room, music.GENERIC_TITLE, "spotify"))

    def test_real_titles_and_resume_are_unchanged(self):
        self.assertEqual(music.parse("play jazz"), (None, "jazz", "spotify"))
        self.assertEqual(music.parse("play music"), (None, None, "spotify"))
        self.assertEqual(music.parse("play something on radio"), (None, "something", "radio"))
        self.assertIsNone(music.parse("music"))

    def test_generic_pick_prefers_favourites_then_curated_categories(self):
        favourite = "spotify://track/" + "b" * 22
        self.assertEqual(music.generic_selection({favourite: 3})[2], "a favourite")
        catalogue = {"categories": {"rock": {"playlists": [PLAYLIST]}, "sexy_time": {"playlists": [PLAYLIST]}}}
        with patch("declan.music.spotify_playlists.listing", return_value=catalogue):
            uri, kind, name = music.generic_selection({})
            self.assertEqual((uri, kind, name), ("https://open.spotify.com/playlist/" + "a" * 22, "playlist", "rock music"))
            # A disliked playlist is never picked; no curated playlists means nothing to pick.
            self.assertIsNone(music.generic_selection({music.media_key(PLAYLIST): 0}))
        with patch("declan.music.spotify_playlists.listing", return_value={"categories": {}}):
            self.assertIsNone(music.generic_selection({}))


class HintTests(unittest.TestCase):
    def compose(self, reply, guest_mode):
        result = turn_response_composition.compose_turn_result(
            "flibber", "s1", None, lighting_context=None, scope=None, response_guest_mode="off", outcome=None,
            routine_turn=None, light_result=None, phrase="flibber", action_results=[], guest_mode=guest_mode,
            visitor_present=False, routine_voice_result=None, routine_status=None,
            converse=lambda *args, **kwargs: {"reply": reply, "session_id": "s1"},
            compose=lambda text, **kwargs: text, apply_outcome_metadata=Mock(), personality=None, lines=None,
            parse_music=None, parse_music_control=None, render_routine=None, response_category=None,
            parse_light_command=None, render_failure=None, composition=None)
        return result.session_response["reply"]

    def test_guests_get_a_hint_after_a_miss(self):
        self.assertEqual(self.compose(UNMATCHED_REPLY, "on"), UNMATCHED_REPLY + GUEST_HINT)
        self.assertEqual(self.compose(UNMATCHED_REPLY, "off"), UNMATCHED_REPLY)
        self.assertEqual(self.compose("Lights on.", "on"), "Lights on.")

    def test_hinted_miss_still_opens_a_retry_and_counts_as_not_understood(self):
        reply = {"reply": UNMATCHED_REPLY + GUEST_HINT}
        session: dict = {}
        session_turn_state.update_turn(
            session, reply, message="flibber the lounge", phrase="flibber the lounge", outcome=None,
            scope="lounge", status_target=None, information_context=None, light_result=None,
            action_results=[], actions=[], unmatched_reply=UNMATCHED_REPLY, now=100.0)
        self.assertTrue(reply["continue_conversation"])
        self.assertEqual(session["pending_retry"]["text"], "flibber the lounge")


CONTEXT = {"music_rooms": ["kitchen", "lounge", "everywhere"], "routines": ["good night"], "areas": ["Kitchen"]}


class GuestHelpTests(unittest.TestCase):

    def test_guest_help_is_short_and_simple(self):
        reply = local_help.answer(("help", None), rows=[], context=CONTEXT, conversation_on=False, guest=True)
        self.assertEqual(reply, local_help.GUEST_HELP)
        self.assertLess(len(reply.split()), 30)
        with_agent = local_help.answer(("help", None), rows=[], context=CONTEXT, conversation_on=True, guest=True)
        self.assertTrue(with_agent.endswith("Or just tell me what you want."))

    def test_household_help_is_unchanged(self):
        reply = local_help.answer(("help", None), rows=[], context=CONTEXT, conversation_on=False)
        self.assertTrue(reply.startswith("I can switch lights"))


if __name__ == "__main__":
    unittest.main()
