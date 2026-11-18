"""Regression tests for the GET access policy."""
import unittest
from types import SimpleNamespace
import get_access_gate_http


class Handler:
    def __init__(self, path, address="198.51.100.10", host="declan.example"):
        self.path = path
        self.client_address = (address, 1234)
        self.headers = {"Host": host}
        self.server = SimpleNamespace(server_port=52737)
        self.result = None

    def send_json(self, status, payload):
        self.result = status, payload


class GetAccessGateTests(unittest.TestCase):
    TOKEN = "a" * 32

    def check(self, path, *, ingress=False, address="198.51.100.10",
              host="declan.example", bearer=None):
        h = Handler(path, address, host)
        if bearer is not None:
            h.headers["Authorization"] = "Bearer " + bearer
        allowed = get_access_gate_http.enforce_access(h, ingress=ingress, token=self.TOKEN)
        return allowed, h.result

    def test_ingress_and_loopback(self):
        self.assertTrue(self.check("/api/settings/export", ingress=True)[0])
        self.assertTrue(self.check("/api/settings/export", address="127.0.0.1",
                                   host="localhost:52737")[0])

    def test_remote_denied(self):
        self.assertEqual(self.check("/api/settings/export")[1][0], 403)
        self.assertEqual(self.check("/api/history")[1][0], 403)

    def test_assist_token_scoped_to_read_only_routes(self):
        self.assertTrue(self.check("/api/history?before=42", bearer=self.TOKEN)[0])
        self.assertTrue(self.check("/api/voicepipeline", bearer=self.TOKEN)[0])
        self.assertTrue(self.check("/api/settings/ai", bearer=self.TOKEN)[0])
        self.assertTrue(self.check("/api/capabilities", bearer=self.TOKEN)[0])
        self.assertFalse(self.check("/api/settings/export", bearer=self.TOKEN)[0])
        self.assertFalse(self.check("/api/history/export", bearer=self.TOKEN)[0])
        self.assertFalse(self.check("/api/history", bearer="wrong")[0])

    def test_local_host_required_for_protected_reads(self):
        self.assertEqual(self.check("/api/history", address="127.0.0.1")[1][0], 403)
        self.assertTrue(self.check("/api/history", address="127.0.0.1",
                                   host="localhost:52737")[0])

    def test_short_token_never_grants_remote_access(self):
        h = Handler("/api/capabilities")
        h.headers["Authorization"] = "Bearer short"
        self.assertFalse(get_access_gate_http.enforce_access(
            h, ingress=False, token="short"))


if __name__ == "__main__":
    unittest.main()
