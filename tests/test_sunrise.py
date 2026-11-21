"""FUT-45: sunrise wake-up: light ramp, good morning, music fade, stop, snooze and restarts."""
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from declan.core.execution_results import ExecutionResult, Outcome
from declan.timers import sunrise, timers
from declan.turn import line_freshness


def local(*args):
    """Timestamp for a local wall-clock time (Monday 23 Nov 2026 is a weekday)."""
    return datetime(*args).astimezone().timestamp()


SUNDAY_NIGHT = local(2026, 11, 22, 22, 0)
WAKE = local(2026, 11, 23, 6, 30)


class FakeHA:
    def __init__(self, lights=None):
        self.calls = []
        self.lights = [["light.bedside", True], ["light.ceiling", False]] if lights is None else lights

    def __call__(self, api, data=None):
        self.calls.append((api, data))
        return self.lights if api == "/api/template" else []

    def service(self, name):
        return [data for api, data in self.calls if api == "/api/services/" + name]


class FakeMusic:
    def __init__(self, player="media_player.bedroom", busy=None, outcome=Outcome.REQUESTED):
        self.player, self.busy, self.outcome = player, busy, outcome
        self.played = []

    def target(self, satellite):
        return self.player, self.busy

    def play(self, title, satellite):
        self.played.append((title, satellite))
        return ExecutionResult("Playing.", self.outcome)


class SunriseTests(unittest.TestCase):
    def setUp(self):
        folder = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(sunrise, "PATH", folder / "sunrise.sqlite3"))
        self.enterContext(patch.object(line_freshness, "PATH", folder / "fresh.sqlite3"))
        self.enterContext(patch.object(line_freshness, "_start_top_up", Mock()))
        self.enterContext(patch.object(timers, "resolve_output",
                                       Mock(return_value=("assist_satellite.bedroom", "Master Bedroom"))))

    def set(self, phrase, now=SUNDAY_NIGHT, satellite="assist_satellite.bedroom"):
        return sunrise.command(sunrise.parse(phrase), None, satellite=satellite, now=now, ha=FakeHA())

    def test_phrases(self):
        self.assertEqual(sunrise.parse("Wake me at 6:30 with the sunrise"), ("set", 6, 30, "once", ""))
        self.assertEqual(sunrise.parse("wake me up at half past six on weekdays with the sunrise"),
                         ("set", 6, 30, "weekdays", ""))
        self.assertEqual(sunrise.parse("wake me at 7 with the sunrise and play Afrikaans"),
                         ("set", 7, 0, "once", "afrikaans"))
        self.assertEqual(sunrise.parse("wake me at 7 with the sunrise every day without music"),
                         ("set", 7, 0, "daily", None))
        self.assertEqual(sunrise.parse("set a sunrise alarm for 6.45 at weekends"), ("set", 6, 45, "weekends", ""))
        self.assertEqual(sunrise.parse("wake me with the sunrise at quarter past six tomorrow"),
                         ("set", 6, 15, "once", ""))
        self.assertEqual(sunrise.parse("when's my sunrise?"), ("ask",))
        self.assertEqual(sunrise.parse("cancel the sunrise alarm"), ("cancel",))
        self.assertEqual(sunrise.parse("skip tomorrow's sunrise"), ("skip",))
        self.assertEqual(sunrise.parse("snooze"), ("snooze",))
        for phrase in ("wake me at 6:30", "what time is sunrise", "play sunrise by norah jones", "turn on the lights"):
            self.assertIsNone(sunrise.parse(phrase), phrase)

    def test_next_wake_follows_the_schedule(self):
        friday_evening = datetime(2026, 11, 27, 20, 0).astimezone()
        weekday = sunrise.next_wake(6, 30, "weekdays", friday_evening)
        weekend = sunrise.next_wake(6, 30, "weekends", friday_evening)
        self.assertEqual(sunrise._local(weekday).weekday(), 0)
        self.assertEqual(sunrise._local(weekend).weekday(), 5)
        self.assertEqual(sunrise.next_wake(6, 30, "once", datetime.fromtimestamp(SUNDAY_NIGHT).astimezone()), WAKE)

    def test_set_replies_and_stores_one_per_room(self):
        result = self.set("wake me at 6:30 with the sunrise")
        self.assertIs(result.outcome, Outcome.TIMER_SET)
        self.assertEqual(result.reply, "Sunrise set for 06:30 tomorrow in the Master Bedroom. "
                                       "The lights start brightening at 06:15, then music.")
        self.set("wake me at 7 with the sunrise on weekdays")
        rows = sunrise.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["hour"], rows[0]["days"], rows[0]["music"]), (7, "weekdays", "something good"))

    def test_lights_ramp_up_to_full_brightness_at_the_wake_time(self):
        self.set("wake me at 6:30 with the sunrise")
        ha, music = FakeHA(), FakeMusic()
        sunrise.due(ha=ha, music=music, now=WAKE - 20 * 60)
        self.assertEqual(ha.calls, [])  # not yet
        sunrise.due(ha=ha, music=music, now=WAKE - 15 * 60)
        first = ha.service("light/turn_on")
        self.assertEqual(first[0]["entity_id"], ["light.bedside"])
        self.assertEqual(first[0]["brightness_pct"], 7)  # heading for the end of the first minute
        self.assertEqual(first[0]["color_temp_kelvin"], 2320)
        self.assertNotIn("color_temp_kelvin", first[1])
        sunrise.due(ha=ha, music=music, now=WAKE - 15 * 60 + 10)
        self.assertEqual(len(ha.service("light/turn_on")), 2)  # one step a minute
        sunrise.due(ha=ha, music=music, now=WAKE - 7.5 * 60)
        self.assertEqual(ha.service("light/turn_on")[-1]["brightness_pct"], 57)
        sunrise.due(ha=ha, music=music, now=WAKE)
        self.assertEqual(ha.service("light/turn_on")[-1]["brightness_pct"], 100)
        announce = ha.service("assist_satellite/announce")[0]
        self.assertIn(announce["message"], sunrise.LINES["wake"])
        self.assertEqual(ha.service("media_player/volume_set")[0],
                         {"entity_id": "media_player.bedroom", "volume_level": sunrise.VOLUME_START})
        self.assertEqual(music.played, [("something good", "assist_satellite.bedroom")])

    def test_music_fades_in_then_the_one_off_finishes(self):
        self.set("wake me at 6:30 with the sunrise")
        ha, music = FakeHA(), FakeMusic()
        for now in (WAKE - 900, WAKE, WAKE + 150, WAKE + 300):
            sunrise.due(ha=ha, music=music, now=now)
        volumes = [data["volume_level"] for data in ha.service("media_player/volume_set")]
        self.assertEqual(volumes, [0.05, 0.15, 0.25])
        sunrise.due(ha=ha, music=music, now=WAKE + sunrise.AWAKE_SECONDS)
        self.assertEqual(sunrise.rows(), [])

    def test_music_playing_elsewhere_is_left_alone_and_mentioned(self):
        self.set("wake me at 6:30 with the sunrise")
        ha, music = FakeHA(), FakeMusic(busy="Kitchen")
        sunrise.due(ha=ha, music=music, now=WAKE - 900)
        sunrise.due(ha=ha, music=music, now=WAKE)
        self.assertIn("Music's already playing in the Kitchen, so I've left it alone.",
                      ha.service("assist_satellite/announce")[0]["message"])
        self.assertEqual(music.played, [])
        self.assertEqual(ha.service("media_player/volume_set"), [])

    def test_no_music_and_lights_already_on_are_respected(self):
        self.set("wake me at 6:30 with the sunrise without music")
        ha, music = FakeHA(lights=[]), FakeMusic()
        sunrise.due(ha=ha, music=music, now=WAKE - 900)
        sunrise.due(ha=ha, music=music, now=WAKE)
        self.assertEqual(ha.service("light/turn_on"), [])
        self.assertEqual(music.played, [])
        self.assertEqual(len(ha.service("assist_satellite/announce")), 1)

    def test_stop_turns_off_the_lights_and_pauses_the_music(self):
        self.set("wake me at 6:30 with the sunrise on weekdays")
        ha, music = FakeHA(), FakeMusic()
        sunrise.due(ha=ha, music=music, now=WAKE - 900)
        sunrise.due(ha=ha, music=music, now=WAKE)
        self.assertTrue(sunrise.active())
        result = sunrise.stop("assist_satellite.bedroom", ha=ha, now=WAKE + 60)
        self.assertIs(result.outcome, Outcome.TIMER_STOPPED)
        self.assertEqual(ha.service("light/turn_off")[0]["entity_id"], ["light.bedside", "light.ceiling"])
        self.assertEqual(ha.service("media_player/media_pause"), [{"entity_id": "media_player.bedroom"}])
        self.assertFalse(sunrise.active())
        row = sunrise.rows()[0]
        self.assertEqual((row["stage"], row["wake_at"]), ("waiting", local(2026, 11, 24, 6, 30)))
        self.assertIsNone(sunrise.stop("assist_satellite.bedroom", ha=ha, now=WAKE + 90))

    def test_snooze_pauses_music_then_wakes_again(self):
        self.set("wake me at 6:30 with the sunrise")
        ha, music = FakeHA(), FakeMusic()
        sunrise.due(ha=ha, music=music, now=WAKE - 900)
        early = sunrise.snooze("assist_satellite.bedroom", ha, now=WAKE - 600)
        self.assertIs(early.outcome, Outcome.UNRESOLVED)
        sunrise.due(ha=ha, music=music, now=WAKE)
        result = sunrise.snooze("assist_satellite.bedroom", ha, now=WAKE + 30)
        self.assertIs(result.outcome, Outcome.TIMER_ADJUSTED)
        self.assertEqual(ha.service("media_player/media_pause"), [{"entity_id": "media_player.bedroom"}])
        sunrise.due(ha=ha, music=music, now=WAKE + 60)
        self.assertEqual(ha.service("media_player/media_play"), [])
        sunrise.due(ha=ha, music=music, now=WAKE + 30 + sunrise.SNOOZE_SECONDS)
        self.assertEqual(ha.service("media_player/media_play"), [{"entity_id": "media_player.bedroom"}])
        self.assertEqual(sunrise.rows()[0]["stage"], "awake")

    def test_survives_a_restart_mid_ramp(self):
        self.set("wake me at 6:30 with the sunrise")
        ha = FakeHA()
        sunrise.due(ha=ha, music=FakeMusic(), now=WAKE - 900)
        # Declan restarts; the next check is worked out from the stored times.
        ha_after = FakeHA()
        sunrise.due(ha=ha_after, music=FakeMusic(), now=WAKE - 300)
        self.assertEqual(ha_after.service("light/turn_on")[0]["brightness_pct"], 73)
        self.assertEqual(ha_after.calls[0][0], "/api/services/light/turn_on")  # lights weren't looked up again

    def test_a_morning_missed_by_more_than_30_minutes_is_skipped(self):
        self.set("wake me at 6:30 with the sunrise every day")
        ha = FakeHA()
        sunrise.due(ha=ha, music=FakeMusic(), now=WAKE + 31 * 60)
        self.assertEqual(ha.calls, [])
        self.assertEqual(sunrise.rows()[0]["wake_at"], local(2026, 11, 24, 6, 30))

    def test_set_late_ramps_from_now(self):
        self.set("wake me at 6:30 with the sunrise", now=WAKE - 300)
        row = sunrise.rows()[0]
        self.assertEqual(row["ramp_start"], WAKE - 300)

    def test_ask_cancel_and_skip(self):
        self.assertIs(self.set("when's my sunrise").outcome, Outcome.NO_TIMER)
        self.set("wake me at 6:30 with the sunrise on weekdays")
        self.assertEqual(self.set("when's my sunrise").reply, "Sunrise in the master bedroom at 06:30 on weekdays.")
        skipped = self.set("skip tomorrow's sunrise")
        self.assertIn("Next sunrise in the master bedroom is at 06:30 on weekdays", skipped.reply)
        self.assertEqual(sunrise.rows()[0]["wake_at"], local(2026, 11, 24, 6, 30))
        self.assertIs(self.set("cancel the sunrise").outcome, Outcome.TIMER_CANCELLED)
        self.assertEqual(sunrise.rows(), [])

    def test_timer_commands_route_stop_and_snooze_only_while_running(self):
        self.enterContext(patch.object(timers, "ringing", Mock(return_value=False)))
        self.assertFalse(timers.matches("stop"))
        self.assertFalse(timers.matches("snooze"))
        self.assertTrue(timers.matches("wake me at 6:30 with the sunrise"))
        self.set("wake me at 6:30 with the sunrise")
        with patch.object(sunrise, "active", Mock(return_value=True)), \
                patch.object(sunrise, "stop", Mock(return_value=ExecutionResult("Off.", Outcome.TIMER_STOPPED))) as stop:
            self.assertTrue(timers.matches("stop"))
            self.assertTrue(timers.matches("snooze"))
            self.assertEqual(timers.handle_result("stop", None, satellite="assist_satellite.bedroom").reply, "Off.")
            stop.assert_called_once()

    def test_dimmable_light_template_and_music_target(self):
        ha = FakeHA(lights=[["light.bedside", True], ["switch.fan", False], "junk"])
        self.assertEqual(sunrise._dimmable_lights(ha, "assist_satellite.bedroom"), [["light.bedside", True]])
        self.assertIn('area_id("assist_satellite.bedroom")', ha.calls[0][1]["template"])
        inventory = [{"entity_id": "assist_satellite.bedroom", "declan_area": "Master Bedroom"}]
        players: dict[str, dict] = {"media_player.bedroom": {"state": "idle"},
                   "media_player.kitchen": {"state": "playing", "attributes": {"friendly_name": "Kitchen"}}}
        music_module = Mock(music_players=Mock(return_value=({"bedroom": "media_player.bedroom"}, players)),
                            room_key=lambda name: " ".join(name.casefold().split()).removeprefix("master "))
        assistant = sunrise.MusicAssistant(music_module, Mock(), Mock(return_value=(inventory, None)))
        self.assertEqual(assistant.target("assist_satellite.bedroom"), ("media_player.bedroom", "Kitchen"))
        players["media_player.kitchen"]["state"] = "paused"
        self.assertEqual(assistant.target("assist_satellite.bedroom"), ("media_player.bedroom", None))


if __name__ == "__main__":
    unittest.main()
