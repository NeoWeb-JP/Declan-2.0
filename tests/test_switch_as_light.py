"""Explicit switch-as-light is never inferred from arbitrary sockets."""
import io
import json
import unittest
import server

class SwitchAsLightTests(unittest.TestCase):
    def test_unmarked_switch_not_controlled(self):
        row = {"entity_id": "switch.garden", "state": "off", "attributes": {"friendly_name": "Garden light"}}
        self.assertIsNone(server.set_switch_as_light("garden light", "on", [row], None))

    def test_marked_switch_requires_verified_state(self):
        row = {"entity_id": "switch.garden", "state": "off", "attributes": {"friendly_name": "Garden light", "declan_as_light": True}}
        class Opener:
            def open(self, request, timeout):
                if request.full_url.endswith("switch.garden"):
                    return io.BytesIO(json.dumps({"state": "on"}).encode())
                return io.BytesIO(b"[]")
        steps = []
        reply, outcome = server.set_switch_as_light("garden light", "on", [row], ("http://ha", {}, Opener()), action_results=steps)
        self.assertEqual(outcome, "confirmed")
        self.assertEqual(steps[0]["entity_id"], "switch.garden")
        self.assertEqual(server.set_switch_as_light("garden light", "on", [row], None, preview=True)[1], "preview")

if __name__ == "__main__":
    unittest.main()
