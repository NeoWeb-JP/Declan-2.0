"""Near-miss light names resolve locally to one clear device, never a guess."""
import unittest

from declan.ha.lighting_execution_dispatch import near_miss

LIGHTS = [("light.kitchen_spots", "Kitchen Spots"), ("light.kitchen_pendant", "Kitchen Pendant"),
          ("light.office_lamp", "Office Lamp"), ("light.lounge_floor_lamp", "Lounge Floor Lamp"),
          ("light.lounge_table_lamp", "Lounge Table Lamp"), ("light.bedroom", "Bedroom")]


def names():
    table: dict[str, set[str]] = {}
    for entity, label in LIGHTS:
        for key in (entity, entity.split(".", 1)[1].replace("_", " "), label.casefold()):
            table.setdefault(key, set()).add(entity)
    return table


class NearMissTests(unittest.TestCase):
    def test_close_names_resolve_to_one_device(self):
        cases = {"kitchen spot": "light.kitchen_spots", "the kitchen spots": "light.kitchen_spots",
                 "office lamps": "light.office_lamp", "kitchen pendent": "light.kitchen_pendant",
                 "bedroom light": "light.bedroom", "bedroom lights": "light.bedroom"}
        for spoken, entity in cases.items():
            with self.subTest(spoken=spoken):
                self.assertEqual(near_miss(names(), spoken), {entity})

    def test_ambiguous_generic_or_unknown_names_are_not_guessed(self):
        for spoken in ("lounge lamp", "lights", "all lights", "lamp", "garage", "kitchen", "xy", ""):
            with self.subTest(spoken=spoken):
                self.assertIsNone(near_miss(names(), spoken))


if __name__ == "__main__":
    unittest.main()
