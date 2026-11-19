"""Regression checks for Movie Time Home Assistant helper extraction."""
import unittest
from unittest.mock import patch

import server
from declan.ha import movie_ha_helpers as helpers
from execution_results import MovieLaunchStatus


class MovieHAExtractionTests(unittest.TestCase):
    def test_remote_wrapper_keeps_request_patch_point(self):
        with patch.object(helpers, "launch_movie_app_result", return_value="sentinel") as extracted:
            self.assertEqual(server.launch_movie_app_result(None, "remote.test", ("App", "app")), "sentinel")
        self.assertIs(extracted.call_args.kwargs["request_factory"], server.Request)

    def test_discovery_wrapper_keeps_inventory_and_area_patch_points(self):
        with patch.object(helpers, "discover_movie_entities", return_value=("script.test", None, None)) as extracted:
            self.assertEqual(server.discover_movie_entities(None, "lounge", script=None, remote=None, needs_remote=True),
                             ("script.test", None, None))
        kwargs = extracted.call_args.kwargs
        self.assertIs(kwargs["inventory_reader"], server.read_ha_inventory_result)
        self.assertIs(kwargs["area_reader"], server.read_ha_areas)
        self.assertIs(kwargs["inventory_module"], server.ha_inventory)

    def test_verification_wrapper_keeps_household_entity_patch_point(self):
        with patch.object(helpers, "verify_legacy_lounge_start", return_value=None) as extracted:
            self.assertIsNone(server.verify_legacy_lounge_start(None, "script.test"))
        kwargs = extracted.call_args.kwargs
        self.assertIs(kwargs["inventory_reader"], server.read_ha_inventory_result)
        self.assertIs(kwargs["entities"], server.household_entities)

    def test_unavailable_remote_never_launches_app(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, *args):
                return b'{"state":"unavailable"}'
        class Opener:
            def __init__(self):
                self.calls = 0
            def open(self, *args, **kwargs):
                self.calls += 1
                return Response()
        opener = Opener()
        result = server.launch_movie_app_result(("http://ha", {}, opener), "remote.test", ("Netflix", "netflix"))
        self.assertEqual(result.status, MovieLaunchStatus.SKIPPED)
        self.assertEqual(opener.calls, 1)


if __name__ == "__main__":
    unittest.main()
