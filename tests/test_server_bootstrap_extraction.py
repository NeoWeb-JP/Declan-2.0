"""Server bootstrap regression contracts."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import server
import server_bootstrap as bootstrap


class BootstrapTests(unittest.TestCase):
    def test_main_preserves_lifecycle_dependencies(self):
        r = Mock()
        r.__doc__ = "server"
        bootstrap.main(r=r)
        kwargs = r.server_lifecycle.main.call_args.kwargs
        self.assertIs(kwargs["handler"], r.Handler)
        self.assertIs(kwargs["ha_connect"], r.ha_device_connection)
        self.assertIs(kwargs["music_inventory"], r.read_music_inventory_result)
        self.assertIs(kwargs["logger"], r.DECLAN_EVENT_LOG)

    def test_set_lights_preserves_legacy_pair(self):
        r = Mock()
        r.set_lights_result.return_value.as_legacy_pair.return_value = ("on", "confirmed")
        self.assertEqual(bootstrap.set_lights("study", "on", brightness=25, r=r), ("on", "confirmed"))
        self.assertEqual(r.set_lights_result.call_args.kwargs["brightness"], 25)

    def test_http_headers_are_secured_before_base_finalize(self):
        calls = []
        handler = object()
        r = SimpleNamespace(
            http_ingress_security=SimpleNamespace(send_security_headers=lambda value: calls.append(("security", value))),
            BaseHTTPRequestHandler=SimpleNamespace(end_headers=lambda value: calls.append(("base", value))),
        )
        bootstrap.end_headers(handler, r=r)
        self.assertEqual(calls, [("security", handler), ("base", handler)])

    def test_run_installs_logs_before_main(self):
        calls = []
        r = SimpleNamespace(
            declan_logs=SimpleNamespace(install=lambda: calls.append("logs")),
            main=lambda: calls.append("main"),
        )
        bootstrap.run(r=r)
        self.assertEqual(calls, ["logs", "main"])

    def test_server_main_uses_live_lifecycle(self):
        with patch.object(server.server_lifecycle, "main", return_value="started") as lifecycle:
            self.assertEqual(server.main(), "started")
            self.assertIs(lifecycle.call_args.kwargs["handler"], server.Handler)


if __name__ == "__main__":
    unittest.main()
