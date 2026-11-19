"""History read route regression contracts."""
import json
import unittest
from types import SimpleNamespace
from declan.http import history_read_routes


class Handler:
    def __init__(self, path):
        self.path = path
        self.result = None

    def send_json(self, status, payload):
        self.result = (status, payload)

    def send_body(self, status, data, content_type, filename):
        self.result = (status, json.loads(data), content_type, filename)


class HistoryReadTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{"id": i, "source": "assist", "message": "lights on"} for i in range(60, 0, -1)]
        self.history = SimpleNamespace(
            recent=lambda before=None, limit=None: [dict(r) for r in self.rows[:limit]],
            learned_intents=lambda: ["alias"],
            normalize_phrase=lambda phrase: phrase,
            verified_recording_turns=lambda ids: {ids[0]: 60},
        )

    def run_route(self, path):
        h = Handler(path)
        history_read_routes.dispatch(h, history=self.history)
        return h.result

    def test_route_matching_is_bounded(self):
        self.assertTrue(history_read_routes.handles("/api/history?before=50"))
        self.assertFalse(history_read_routes.handles("/api/history/other"))
        self.assertFalse(history_read_routes.handles("/api/history/export?x=1"))
        with self.assertRaises(ValueError):
            self.run_route("/api/history/other")

    def test_pagination_and_cursor_errors(self):
        result = self.run_route("/api/history")
        self.assertEqual(result[0], 200)
        self.assertEqual(len(result[1]["turns"]), 50)
        self.assertEqual(result[1]["next"], 11)
        self.assertEqual(result[1]["learned_intents"], ["alias"])
        self.assertTrue(result[1]["turns"][0]["teachable"])
        self.assertIsNone(self.run_route("/api/history?before=10")[1]["learned_intents"])
        for cursor in ("0", "-1", "xyz", str(2**63)):
            self.assertEqual(self.run_route("/api/history?before=" + cursor)[0], 400)

    def test_export_and_recording_links(self):
        result = self.run_route("/api/history/export")
        self.assertEqual(result[0], 200)
        self.assertEqual(result[1]["turns"][0]["id"], 1)
        self.assertEqual(result[3], "declan-conversation-history.json")
        self.assertEqual(self.run_route("/api/history/recording-links?ids=abc")[1]["links"],
                         {"abc": 60})
        self.assertEqual(self.run_route("/api/history/recording-links?wrong=abc")[0], 400)

    def test_storage_errors(self):
        self.history.recent = lambda *a, **k: (_ for _ in ()).throw(OSError())
        for path in ("/api/history", "/api/history/export",
                     "/api/history/recording-links?ids=abc"):
            self.assertEqual(self.run_route(path)[0], 503)


if __name__ == "__main__":
    unittest.main()
