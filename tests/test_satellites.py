"""FUT-32: what each satellite can do, from Home Assistant with Settings overrides."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from declan.core.execution_results import Outcome
from declan.ha import intercom, satellites
from declan.turn import house_questions

ROWS: list[list] = [["assist_satellite.kitchen", "Kitchen", "Kitchen", "idle", 3, 1],
        ["assist_satellite.lounge", "Lounge", "Lounge", "idle", 3, 2],
        ["assist_satellite.master_bedroom", "Master Bedroom", "Bedroom", "idle", 3, 1],
        ["assist_satellite.utility", "Utility Room", "Utility", "idle", 0, 0]]
INTERCOM_ROWS = [[row[0], row[1], "Ground floor", row[3], "dev-" + str(row[0])[17:]] for row in ROWS]


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
    def __init__(self):
        self.announced = []

    def open(self, request, timeout=None):
        data = json.loads(request.data)
        if request.full_url.endswith("/api/template"):
            return Response(ROWS if "supported_features" in data["template"] else INTERCOM_ROWS)
        self.announced.append(data["entity_id"])
        return Response([])


class RegistryTestCase(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.enterContext(patch.object(satellites, "PATH", Path(tmp.name) / "caps.json"))


class RegistryTests(RegistryTestCase):
    def test_capabilities_from_home_assistant(self):
        rows = satellites.read(lambda template: ROWS)
        self.assertEqual([row["area"] for row in rows], ["Kitchen", "Lounge", "Master Bedroom", "Utility Room"])
        kitchen = rows[0]["capabilities"]
        self.assertEqual(kitchen, {"audio": True, "announce": True, "reply": True, "screen": False})
        self.assertEqual(rows[3]["capabilities"], {"audio": False, "announce": False, "reply": False, "screen": False})

    def test_overrides_win_and_can_be_cleared(self):
        satellites.save("assist_satellite.kitchen", {"screen": True, "reply": False})
        kitchen = satellites.read(lambda template: ROWS)[0]
        self.assertEqual(kitchen["overrides"], {"screen": True, "reply": False})
        self.assertEqual(kitchen["capabilities"]["screen"], True)
        self.assertEqual(kitchen["detected"]["reply"], True)
        self.assertEqual(satellites.save("assist_satellite.kitchen", {"screen": None, "reply": None}), {})
        self.assertEqual(satellites.read(lambda template: ROWS)[0]["overrides"], {})
        for bad in (("light.kitchen", {"screen": True}), ("assist_satellite.kitchen", {"telly": True}),
                    ("assist_satellite.kitchen", {"screen": "yes"})):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                satellites.save(*bad)

    def test_can(self):
        rows = satellites.read(lambda template: ROWS)
        self.assertTrue(satellites.can(rows, "assist_satellite.kitchen", "announce"))
        self.assertFalse(satellites.can(rows, "assist_satellite.utility", "announce"))
        self.assertIsNone(satellites.can(rows, "assist_satellite.garage", "announce"))

    def test_describe_and_voice(self):
        rows = satellites.read(lambda template: ROWS)
        self.assertEqual(satellites.describe(rows[0]), "The kitchen can play audio, take announcements and listen "
                                                       "for a reply, but can't show pictures.")
        connection: tuple = ("http://ha", {}, FakeHA())
        self.assertEqual(house_questions.match("what can the satellites do"), ("satellites", ("satellites", None)))
        everyone = satellites.result(("satellites", None), connection)
        self.assertEqual(everyone.reply.count("The "), 4)
        here = satellites.result(("satellites", "here"), connection, origin="assist_satellite.lounge")
        self.assertTrue(here.reply.startswith("The lounge can play audio"))
        self.assertEqual(satellites.result(("satellites", "here"), connection, origin=None).outcome, Outcome.UNRESOLVED)
        self.assertEqual(satellites.result(("satellites", "garage"), connection).outcome, Outcome.UNRESOLVED)
        self.assertTrue(satellites.result(("satellites", "master bedroom"), connection).reply.startswith(
            "The master bedroom"))

    def test_home_assistant_down(self):
        class Down:
            def open(self, request, timeout=None):
                raise OSError("down")
        self.assertEqual(satellites.result(("satellites", None), ("http://ha", {}, Down())).outcome,
                         Outcome.UNAVAILABLE)


class IntercomUsesTheRegistryTests(RegistryTestCase):
    def test_satellite_that_cannot_announce_is_reported_not_called(self):
        ha = FakeHA()
        result = intercom.result(("announce", None, "dinner's ready"), ("http://ha", {}, ha),
                                 origin="assist_satellite.lounge", quiet=False)
        self.assertNotIn("assist_satellite.utility", ha.announced)
        self.assertEqual(result.outcome, Outcome.PARTIAL)
        self.assertIn("Utility Room can't take announcements.", result.reply)

    def test_only_target_cannot_announce(self):
        ha = FakeHA()
        result = intercom.result(("tell", "utility room dinner's ready"), ("http://ha", {}, ha),
                                 origin="assist_satellite.lounge", quiet=False)
        self.assertEqual((result.outcome, ha.announced), (Outcome.UNRESOLVED, []))

    def test_override_lets_it_announce(self):
        satellites.save("assist_satellite.utility", {"announce": True})
        ha = FakeHA()
        intercom.result(("tell", "utility room dinner's ready"), ("http://ha", {}, ha),
                        origin="assist_satellite.lounge", quiet=False)
        self.assertEqual(ha.announced, ["assist_satellite.utility"])


class HouseholdViewTests(RegistryTestCase):
    def test_validation(self):
        from tests.test_household_settings import load_view
        view, _ = load_view()
        self.assertTrue(view.valid_satellite_change({"save_satellite": {"entity_id": "assist_satellite.kitchen",
                                                                        "screen": True, "reply": None}}))
        self.assertFalse(view.valid_satellite_change({"save_satellite": {"entity_id": "light.x", "screen": True}}))
        self.assertFalse(view.valid_satellite_change({"save_satellite": {"entity_id": "assist_satellite.k",
                                                                         "telly": True}}))
        self.assertTrue(view.valid_satellites(None))
        self.assertTrue(view.valid_satellites(satellites.read(lambda template: ROWS)))
        self.assertFalse(view.valid_satellites([{"entity_id": "assist_satellite.k"}]))


if __name__ == "__main__":
    unittest.main()
