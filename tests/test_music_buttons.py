"""Explicit MA targets reuse the real Spotify search and playback path."""
import unittest
import test_music as music_fixture
import music


class MusicButtonTests(unittest.TestCase):
    setUp = music_fixture.MusicTests.setUp
    open = music_fixture.MusicTests.open
    play = music_fixture.MusicTests.play

    def register(self):
        for entity, row in self.players.items():
            row.update(declan_music_assistant=True, declan_area='Kitchen' if entity == self.kitchen else 'House')
        self.players[self.kitchen]['attributes'] = {'friendly_name': 'Kitchen Declan Voice Assistant'}
        for entity in ('media_player.kitchen_sonos', 'media_player.kitchen_tv'):
            self.players[entity] = {'entity_id': entity, 'state': 'idle', 'attributes': {},
                                    'declan_area': 'Kitchen', 'declan_music_assistant': True}

    def test_ambiguous_room_is_unchanged_but_explicit_target_searches_and_plays(self):
        self.register()
        self.search_results = {'playlists': [{'name': '80s Music', 'id': 'A' * 22}]}
        self.assertEqual(self.play('play 80s music in the kitchen on spotify')[1], 'unresolved')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.searches, [])
        reply, outcome = self.play(f'play 80s music in the {self.kitchen} on spotify')
        self.assertEqual(outcome, 'confirmed', reply)
        self.assertTrue(self.searches)  # Uses music.py Spotify search, not a saved stream URL.
        self.assertEqual(self.spotify_tokens, 1)
        self.assertEqual(self.calls[-1][0], 'play_media')
        self.assertEqual(self.calls[-1][1]['entity_id'], self.kitchen)
        self.assertIsNotNone(music.SPOTIFY_REFERENCE.fullmatch(self.calls[-1][1]['media_id']))
        self.assertEqual(self.calls[-1][1]['media_type'], 'playlist')
        self.assertIn('Kitchen Declan Voice Assistant', reply)
        self.assertNotIn('media_player.kitchen_sonos', [data['entity_id'] for _, data in self.calls])
        self.assertEqual(self.players[self.bedroom]['state'], 'idle')  # Single-stream handoff preserved.

    def test_unknown_malformed_and_non_ma_targets_do_not_search_or_change_playback(self):
        self.register()
        self.players['media_player.native_echo'] = {'entity_id': 'media_player.native_echo', 'state': 'idle',
                                                   'attributes': {}, 'declan_music_assistant': False}
        for target in ('media_player.missing', 'media_player.native_echo', 'media_player.bad;target'):
            with self.subTest(target=target):
                self.assertEqual(self.play(f'play country music in the {target} on spotify')[1], 'unresolved')
        self.assertEqual(self.searches, [])
        self.assertEqual(self.calls, [])

    def test_unavailable_explicit_target_does_not_fall_back_to_another_kitchen_player(self):
        self.register()
        for state in ('unavailable', 'unknown'):
            self.players[self.kitchen]['state'] = state
            self.assertEqual(self.play(f'play classical music in the {self.kitchen} on spotify')[1], 'unavailable')
        self.assertEqual(self.searches, [])
        self.assertEqual(self.calls, [])

    def test_explicit_target_needs_registry_evidence_even_in_legacy_inventory(self):
        self.assertEqual(self.play(f'play country music in the {self.kitchen} on spotify')[1], 'unresolved')
        self.assertEqual(self.searches, [])
        self.assertEqual(self.calls, [])
