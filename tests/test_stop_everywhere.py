"""Issue #12: Stop targets every active approved Music Assistant destination."""
import unittest
from unittest.mock import patch
import legacy_wire
import server

class StopEverywhereTests(unittest.TestCase):
    def test_stops_all_active_approved_players(self):
        inventory=[{"entity_id":"media_player.everywhere","state":"playing"},
                   {"entity_id":"media_player.kitchen","state":"playing"}]
        with patch.object(server,'read_music_inventory_result',return_value=(inventory,None)), \
             patch.object(server.music,"music_players",return_value=(
                 {"everywhere":"media_player.everywhere","kitchen":"media_player.kitchen"},{
                     "media_player.everywhere":{"state":"playing"},
                     "media_player.kitchen":{"state":"playing"}})), \
             patch.object(server.music,"request") as request, \
             patch.object(server.music,"wait_for",return_value=True):
            reply,outcome,detail=legacy_wire.stop_everywhere_output(("url",{},None))
        self.assertEqual(outcome,"confirmed")
        self.assertEqual(request.call_count,2)
    def test_unverified_stop_is_not_reported_as_success(self):
        with patch.object(server,'read_music_inventory_result',return_value=([],None)), \
             patch.object(server.music,"music_players",return_value=(
                 {"everywhere":"media_player.everywhere"},{
                     "media_player.everywhere":{"state":"playing"}})), \
             patch.object(server.music,"request"), \
             patch.object(server.music,"wait_for",return_value=False):
            self.assertEqual(legacy_wire.stop_everywhere_output(("url",{},None))[1],"unverified")

if __name__=="__main__":
    unittest.main()
