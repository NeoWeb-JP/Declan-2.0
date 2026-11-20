"""Music starts at a sensible volume: louder speakers are turned down first."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from declan.music import music
from test_music import MusicFixture


class StartVolumeSettingTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(TemporaryDirectory())
        self.path = Path(folder) / "music-settings.json"
        self.enterContext(patch.object(music, "music_settings_path", lambda: self.path))

    def level(self, value):
        env = {} if value is None else {"DECLAN_MUSIC_START_VOLUME": value}
        with patch.dict(music.os.environ, env, clear=False):
            if value is None:
                music.os.environ.pop("DECLAN_MUSIC_START_VOLUME", None)
            return music.start_volume()

    def test_default_is_thirty_percent(self):
        for value in (None, "", "  ", "loud"):
            with self.subTest(value=value):
                self.assertEqual(self.level(value), 0.30)

    def test_zero_turns_it_off_and_values_are_bounded(self):
        self.assertIsNone(self.level("0"))
        self.assertIsNone(self.level("-5"))
        self.assertEqual(self.level("45"), 0.45)
        self.assertEqual(self.level("150"), 1.0)

    def test_value_saved_in_settings_wins_and_survives_an_older_panel_save(self):
        switches = {"reply_first": True, "music_assistant_search": False}
        music.music_settings.save(self.path, switches, 20)
        self.assertEqual(self.level("45"), 0.20)
        music.music_settings.save(self.path, switches)
        self.assertEqual(music.music_settings.listing(self.path)["start_volume"],
                         {"percent": 20, "source": "saved"})
        music.music_settings.save(self.path, switches, 0)
        self.assertIsNone(self.level(None))

    def test_invalid_saved_values_are_refused(self):
        switches = {"reply_first": True, "music_assistant_search": False}
        for value in (101, -1, 30.5, "30", True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                music.music_settings.save(self.path, switches, value)

    def test_group_members_are_turned_down_not_the_group(self):
        players = {"media_player.all": {"attributes": {"group_members": [
                       "media_player.kitchen", "media_player.lounge", "media_player.gone"]}},
                   "media_player.kitchen": {}, "media_player.lounge": {}}
        self.assertEqual(music._start_volume_targets("media_player.all", players),
                         ["media_player.kitchen", "media_player.lounge"])
        self.assertEqual(music._start_volume_targets("media_player.kitchen", players),
                         ["media_player.kitchen"])


class StartVolumePlaybackTests(MusicFixture):
    def setUp(self):
        super().setUp()
        folder = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.object(music, "music_settings_path",
                                       lambda: Path(folder) / "music-settings.json"))
        self.enterContext(patch.dict(music.os.environ, {"DECLAN_MUSIC_START_VOLUME": "30"}))

    def volume_calls(self):
        return [data for name, data in self.calls if name == "volume_set"]

    def test_loud_speaker_is_turned_down_before_playback_starts(self):
        self.players[self.bedroom]["state"] = "idle"
        self.players[self.bedroom]["attributes"] = {"volume_level": 0.8}
        reply, outcome = self.play("play jazz in the bedroom")
        self.assertEqual(self.volume_calls(), [{"entity_id": self.bedroom, "volume_level": 0.3}], reply)
        names = [name for name, _ in self.calls]
        self.assertLess(names.index("volume_set"), names.index("play_media"))

    def test_quieter_speaker_is_left_alone(self):
        self.players[self.bedroom]["state"] = "idle"
        self.players[self.bedroom]["attributes"] = {"volume_level": 0.2}
        self.play("play jazz in the bedroom")
        self.assertEqual(self.volume_calls(), [])

    def test_turned_off_sends_no_volume_change(self):
        self.players[self.bedroom]["state"] = "idle"
        self.players[self.bedroom]["attributes"] = {"volume_level": 0.8}
        with patch.dict(music.os.environ, {"DECLAN_MUSIC_START_VOLUME": "0"}):
            self.play("play jazz in the bedroom")
        self.assertEqual(self.volume_calls(), [])

    def test_a_failed_volume_change_never_blocks_playback(self):
        self.players[self.bedroom]["state"] = "idle"
        self.players[self.bedroom]["attributes"] = {"volume_level": 0.8}
        real = music.request

        def flaky(connection, path, data=None, **kwargs):
            if path.endswith("/volume_set"):
                raise TimeoutError
            return real(connection, path, data, **kwargs)

        with patch.object(music, "request", side_effect=flaky):
            reply, outcome = self.play("play jazz in the bedroom")
        self.assertIn("play_media", [name for name, _ in self.calls], reply)


if __name__ == "__main__":
    unittest.main()
