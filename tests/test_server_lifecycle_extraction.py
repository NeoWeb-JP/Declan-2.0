"""Regression checks for server lifecycle extraction and CLI safety gates."""
import unittest
from unittest.mock import patch

import server
import server_lifecycle


class ServerLifecycleExtractionTests(unittest.TestCase):
    def test_main_delegates_with_live_dependencies(self):
        with patch.object(server_lifecycle, "main", return_value="sentinel") as runner:
            self.assertEqual(server.main(), "sentinel")
        kwargs = runner.call_args.kwargs
        self.assertIs(kwargs["history_store"], server.history)
        self.assertIs(kwargs["timer_store"], server.timers)
        self.assertIs(kwargs["server_factory"], server.ThreadingHTTPServer)
        self.assertIs(kwargs["handler"], server.Handler)
        self.assertIs(kwargs["clock"], server.monotonic)
        self.assertIs(kwargs["music_module"], server.music)
        self.assertIs(kwargs["updates_module"], server.updates)

    def test_assist_lan_requires_strong_token_before_initialization(self):
        with patch.object(server.history, "initialize") as initialize:
            with self.assertRaises(SystemExit) as error:
                server_lifecycle.main(
                    description="test", argv=["--assist-lan"],
                    environ={"DECLAN_ASSIST_TOKEN": "short"},
                    history_store=server.history, timer_store=server.timers,
                    server_factory=server.ThreadingHTTPServer, handler=server.Handler,
                    thread_factory=server.Thread, clock=server.monotonic,
                    opener_factory=server.build_opener, proxy_factory=server.ProxyHandler,
                    logger=server.DECLAN_EVENT_LOG, updates_module=server.updates,
                    music_module=server.music, ha_connect=server.ha_device_connection,
                    music_inventory=server.read_music_inventory_result,
                    ip_address=server.ipaddress.ip_address, assist_port=server.ASSIST_PORT,
                )
        self.assertEqual(error.exception.code, 2)
        initialize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
