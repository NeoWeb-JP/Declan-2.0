"""FUT-46: entrance themes play once per real arrival, never in quiet hours, Guest mode or over music."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from declan.ha import entrance_themes as themes

CLIP = "media-source://media_source/local/themes/jaco.mp3"
T0 = 1_800_000_000.0


class FakeHA:
    def __init__(self):
        self.people = {"person.jaco": "home", "person.edd": "home"}
        self.guest, self.busy = "off", False
        self.calls = []

    def __call__(self, api, data=None):
        self.calls.append((api, data))
        if api == "/api/template":
            return {"people": [[person, state, person.split(".")[1].capitalize()] for person, state in self.people.items()],
                    "guest": self.guest, "busy": self.busy}
        return []

    def played(self):
        return [data for api, data in self.calls if api == "/api/services/assist_satellite/announce"]


class EntranceThemeTests(unittest.TestCase):
    def setUp(self):
        folder = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(themes, "PATH", folder / "themes.sqlite3"))
        self.enterContext(patch.dict("os.environ", {"DECLAN_ENTRANCE_SATELLITE": ""}))
        self.ha = FakeHA()

    def due(self, now, quiet=False):
        return themes.due(self.ha, now=now, quiet=quiet, guest_entity="input_boolean.guest_mode")

    def setup_jaco(self):
        self.due(T0)  # first sight: recorded only
        themes.save_satellite("assist_satellite.hallway")
        themes.save_theme("person.jaco", CLIP, True)

    def leave_and_return(self, away_for=30 * 60, start=T0 + 60, quiet=False):
        self.ha.people["person.jaco"] = "not_home"
        self.due(start)
        self.ha.people["person.jaco"] = "home"
        return self.due(start + away_for, quiet=quiet)

    def test_first_sight_and_restart_never_play(self):
        self.setup_jaco()
        self.assertEqual(self.ha.played(), [])
        self.ha.people["person.jaco"] = "unavailable"  # HA restarting
        self.due(T0 + 10)
        self.ha.people["person.jaco"] = "home"
        self.assertEqual(self.due(T0 + 20), [])

    def test_a_real_arrival_plays_once(self):
        self.setup_jaco()
        self.assertEqual(self.leave_and_return(), ["person.jaco"])
        self.assertEqual(self.ha.played(), [{"entity_id": "assist_satellite.hallway", "media_id": CLIP,
                                             "preannounce": False}])
        self.assertEqual(self.due(T0 + 4000), [])  # still home: nothing more

    def test_short_trips_and_quick_repeats_do_not_play(self):
        self.setup_jaco()
        self.assertEqual(self.leave_and_return(away_for=5 * 60), [])  # phone flicked to away
        self.assertEqual(self.leave_and_return(start=T0 + 1000), ["person.jaco"])
        # Played at T0 + 2800; back again 11 minutes later is within the 30-minute repeat guard.
        self.assertEqual(self.leave_and_return(away_for=11 * 60, start=T0 + 2810), [])

    def test_quiet_hours_guest_mode_and_music_block_it_and_it_is_not_played_later(self):
        self.setup_jaco()
        self.assertEqual(self.leave_and_return(quiet=True), [])
        self.ha.guest = "on"
        self.assertEqual(self.leave_and_return(start=T0 + 10_000), [])
        self.ha.guest, self.ha.busy = "off", True
        self.assertEqual(self.leave_and_return(start=T0 + 20_000), [])
        self.ha.busy = False
        self.assertEqual(self.due(T0 + 30_000), [])
        self.assertEqual(self.ha.played(), [])

    def test_unknown_guest_mode_counts_as_on(self):
        self.setup_jaco()
        self.ha.guest = "unavailable"
        self.assertEqual(self.leave_and_return(), [])

    def test_switched_off_or_no_satellite_does_not_play(self):
        self.setup_jaco()
        themes.save_theme("person.jaco", CLIP, False)
        self.assertEqual(self.leave_and_return(), [])
        themes.save_theme("person.jaco", CLIP, True)
        themes.save_satellite("")
        self.assertEqual(self.leave_and_return(start=T0 + 10_000), [])

    def test_someone_first_seen_away_gets_a_theme_when_they_arrive(self):
        self.ha.people["person.jaco"] = "not_home"
        self.due(T0)
        themes.save_satellite("assist_satellite.hallway")
        themes.save_theme("person.jaco", CLIP, True)
        self.ha.people["person.jaco"] = "home"
        self.assertEqual(self.due(T0 + 20 * 60), ["person.jaco"])

    def test_settings_validation_listing_and_try_it(self):
        self.due(T0)
        with self.assertRaises(ValueError):
            themes.save_theme("person.jaco", "https://example.com/x.mp3", True)
        with self.assertRaises(ValueError):
            themes.save_theme("person.jaco", "", True)
        with self.assertRaises(ValueError):
            themes.save_theme("person.nobody", CLIP, True)
        with self.assertRaises(ValueError):
            themes.save_satellite("media_player.hallway")
        with self.assertRaises(ValueError):
            themes.try_theme("person.jaco", self.ha)  # no satellite yet
        themes.save_satellite("assist_satellite.hallway")
        themes.save_theme("person.jaco", CLIP, True)
        listing = themes.listing()
        self.assertEqual(listing["satellite"], "assist_satellite.hallway")
        self.assertEqual([row["name"] for row in listing["people"]], ["Edd", "Jaco"])
        self.assertTrue(listing["people"][1]["enabled"])
        themes.try_theme("person.jaco", self.ha)
        self.assertEqual(self.ha.played()[0]["media_id"], CLIP)
        with self.assertRaises(ValueError):
            themes.try_theme("person.edd", self.ha)

    def test_home_assistant_unavailable_touches_nothing(self):
        def broken(api, data=None):
            raise ValueError("Home Assistant is not configured")
        self.assertEqual(themes.due(broken, now=T0, quiet=False, guest_entity="input_boolean.guest_mode"), [])
        self.assertFalse(themes.PATH.exists())

    def test_environment_satellite_until_saved(self):
        with patch.dict("os.environ", {"DECLAN_ENTRANCE_SATELLITE": "assist_satellite.front_door"}):
            self.assertEqual(themes.satellite(), "assist_satellite.front_door")
            themes.save_satellite("")
            self.assertEqual(themes.satellite(), "")


class HouseholdProxyThemeTests(unittest.TestCase):
    def test_change_bodies(self):
        from tests.test_household_settings import load_view
        view, _ = load_view()
        self.assertTrue(view.valid_theme_change({"save_theme": {"person": "person.jaco", "media_id": CLIP, "enabled": True}}))
        self.assertTrue(view.valid_theme_change({"theme_satellite": ""}))
        self.assertTrue(view.valid_theme_change({"theme_satellite": "assist_satellite.hallway"}))
        self.assertTrue(view.valid_theme_change({"try_theme": "person.jaco"}))
        self.assertFalse(view.valid_theme_change({"theme_satellite": "media_player.x"}))
        self.assertFalse(view.valid_theme_change({"save_theme": {"person": "light.x", "media_id": CLIP, "enabled": True}}))
        self.assertFalse(view.valid_theme_change({"save_theme": {"person": "person.jaco", "media_id": CLIP, "enabled": "yes"}}))
        self.assertTrue(view.valid_themes(None))
        self.assertTrue(view.valid_themes({"satellite": "", "people": [
            {"person": "person.jaco", "name": "Jaco", "media_id": "", "enabled": False, "home": True, "played_at": None}]}))
        self.assertFalse(view.valid_themes({"satellite": "", "people": [{"person": "person.jaco"}]}))


if __name__ == "__main__":
    unittest.main()
