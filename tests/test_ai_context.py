import unittest
from ai_context import select


class AIContextTests(unittest.TestCase):
    def test_large_inventory_uses_room_context(self):
        rows = [{"entity_id": f"light.device_{i}", "declan_area": "Lounge" if i < 4 else "Other",
                 "attributes": {"friendly_name": f"Device {i}"}} for i in range(130)]
        chosen = select(rows, "turn on the lounge lights")
        self.assertEqual(len(chosen), 4)

    def test_ambiguous_large_inventory_fails_closed(self):
        rows = [{"entity_id": f"light.device_{i}", "attributes": {}} for i in range(130)]
        with self.assertRaises(ValueError):
            select(rows, "turn on all lights")

    def test_small_inventory_remains_complete(self):
        rows = [{"entity_id": "light.kitchen"}]
        self.assertEqual(select(rows, "turn on lights"), rows)


if __name__ == "__main__":
    unittest.main()
