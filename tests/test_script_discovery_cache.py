"""Script discovery cache credential isolation and refresh race regressions."""

import io
import json
import threading
import unittest
from unittest.mock import Mock, patch

import script_discovery
from script_discovery_cache import ScriptDiscoveryCache


def payload(name):
    return {"inspection": "complete", "scripts": [
        {"entity_id": "script." + name, "name": name, "safe": True}]}


def connection(token, opener, url="http://ha"):
    return url, {"Authorization": "Bearer " + token}, opener


class DiscoveryCacheTests(unittest.TestCase):
    def setUp(self):
        self.cache = ScriptDiscoveryCache(max_entries=2)
        self.enterContext(patch.object(script_discovery, "CACHE", self.cache))

    def test_different_credentials_at_same_url_do_not_share_results(self):
        opener = Mock()
        opener.open.side_effect = [
            io.BytesIO(json.dumps(payload("morning")).encode()),
            io.BytesIO(json.dumps(payload("night")).encode()),
        ]
        first = script_discovery.discover_result(connection("one", opener))
        second = script_discovery.discover_result(connection("two", opener))
        self.assertNotEqual(first.scripts, second.scripts)
        self.assertIs(script_discovery.discover_result(connection("one", opener)), first)
        self.assertEqual(opener.open.call_count, 2)

    def test_reordered_identical_headers_share_cache_and_key_hides_secrets(self):
        key1 = self.cache.key("http://ha", {"Authorization": "Bearer secret", "X-Scope": "a"})
        key2 = self.cache.key("http://ha", {"x-scope": "a", "authorization": "Bearer secret"})
        self.assertEqual(key1, key2)
        self.assertNotIn(b"secret", key1)
        self.assertNotEqual(key1, self.cache.key("http://ha", {"Authorization": "Bearer other"}))

    def test_out_of_order_refresh_keeps_newest_result(self):
        old_started = threading.Event()
        allow_old = threading.Event()
        opener = Mock()
        results = {}

        def open_request(request, timeout):
            if threading.current_thread().name == "old-request":
                old_started.set()
                if not allow_old.wait(5):
                    raise TimeoutError("fixture timeout")
                return io.BytesIO(json.dumps(payload("old")).encode())
            return io.BytesIO(json.dumps(payload("new")).encode())

        opener.open.side_effect = open_request

        def run_old():
            results["old"] = script_discovery.discover_result(
                connection("one", opener), fresh=True)

        old = threading.Thread(target=run_old, name="old-request")
        old.start()
        self.assertTrue(old_started.wait(5))
        new = script_discovery.discover_result(connection("one", opener), fresh=True)
        allow_old.set()
        old.join(timeout=5)
        self.assertFalse(old.is_alive())
        self.assertEqual(new.scripts[0]["entity_id"], "script.new")
        self.assertEqual(results["old"].scripts[0]["entity_id"], "script.old")
        self.assertIs(script_discovery.discover_result(connection("one", opener)), new)

    def test_bounded_cache_does_not_retain_expired_scopes(self):
        for n in range(3):
            key = self.cache.key("http://ha", {"Authorization": str(n)})
            epoch = self.cache.begin(key)
            self.assertTrue(self.cache.publish(key, epoch, n))
        self.assertEqual(len(self.cache._entries), 2)
        self.assertIsNone(self.cache.get(self.cache.key(
            "http://ha", {"Authorization": "0"}), seconds=30))

    def test_failed_fetch_is_not_cached(self):
        opener = Mock()
        opener.open.side_effect = TimeoutError()
        target = connection("one", opener)
        self.assertIsNotNone(script_discovery.discover_result(target).error)
        self.assertIsNotNone(script_discovery.discover_result(target).error)
        self.assertEqual(opener.open.call_count, 2)


if __name__ == "__main__":
    unittest.main()
