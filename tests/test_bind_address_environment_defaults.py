"""Verify Declan server bind-address environment behaviour."""
import os
import io
import unittest
from argparse import Namespace
from contextlib import redirect_stderr
from unittest.mock import patch

import server


class BindAddressEnvironmentTests(unittest.TestCase):
    def launch(self, *, assist_lan, environment):
        addresses = []

        def reject_socket(address, _handler):
            addresses.append(address)
            raise OSError("test listener disabled")

        args = Namespace(assist_lan=assist_lan, port=None)
        with patch.dict(os.environ, environment, clear=True), patch.object(
                server.argparse.ArgumentParser, "parse_args", return_value=args), patch.object(
                server.history, "retention_seconds", return_value=86400), patch.object(
                server.history, "initialize"), patch.object(
                server.timers, "initialize"), patch.object(
                server, "ThreadingHTTPServer", side_effect=reject_socket):
            stderr = io.StringIO()
            with redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
                server.main()
        return addresses, error.exception.code, stderr.getvalue()

    def test_non_lan_ignores_environment_override(self):
        addresses, _, _ = self.launch(assist_lan=False, environment={
            "DECLAN_BIND_ADDRESS": "0.0.0.0"})
        self.assertEqual(addresses, [("127.0.0.1", 8765)])

    def test_lan_defaults_to_all_ipv4_interfaces(self):
        addresses, _ = self.launch(assist_lan=True, environment={
            "DECLAN_ASSIST_TOKEN": "a" * 32})
        self.assertEqual(addresses, [("0.0.0.0", server.ASSIST_PORT)])

    def test_lan_accepts_explicit_ipv4_override(self):
        addresses, _ = self.launch(assist_lan=True, environment={
            "DECLAN_ASSIST_TOKEN": "a" * 32,
            "DECLAN_BIND_ADDRESS": "192.168.1.10"})
        self.assertEqual(addresses, [("192.168.1.10", server.ASSIST_PORT)])

    def test_invalid_lan_bind_addresses_fail_before_socket(self):
        for value in ("", "localhost", "::1", "192.168.1.999", " 127.0.0.1 "):
            with self.subTest(value=value):
                addresses, code, error = self.launch(assist_lan=True, environment={
                    "DECLAN_ASSIST_TOKEN": "a" * 32,
                    "DECLAN_BIND_ADDRESS": value})
                self.assertEqual(addresses, [])
                self.assertEqual(code, 2)
                self.assertIn("DECLAN_BIND_ADDRESS must be an IPv4 address", error)

    def test_lan_requires_sufficient_assist_token_before_socket(self):
        for token in ("", "short", "a" * 31):
            with self.subTest(token=token):
                addresses, error = self.launch(assist_lan=True, environment={
                    "DECLAN_ASSIST_TOKEN": token})
                self.assertEqual(addresses, [])
                self.assertIn("at least 32 characters", error)


if __name__ == "__main__":
    unittest.main()
