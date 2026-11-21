"""FUT-64: under load, extra requests are turned away quickly and voice turns keep their room."""
import socket
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler
from threading import Event, Thread
from time import monotonic, sleep

from declan_ingress import http_server
from declan_ingress.http_server import BoundedHTTPServer


def handler(release):
    class Handler(BaseHTTPRequestHandler):
        def _answer(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            if not self.path.startswith("/fast"):
                release.wait(5)
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = do_POST = _answer

        def log_message(self, *args):
            pass
    return Handler


class LoadTestCase(unittest.TestCase):
    def serve(self, max_workers, **kwargs):
        self.release = Event()
        server = BoundedHTTPServer(("127.0.0.1", 0), handler(self.release), max_workers=max_workers, **kwargs)
        Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.addCleanup(self.release.set)
        self.port = server.server_port
        return server

    def request(self, method="GET", path="/", timeout=6):
        started = monotonic()
        connection = HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        try:
            connection.request(method, path, body=b"{}" if method == "POST" else None)
            return connection.getresponse().status, monotonic() - started
        finally:
            connection.close()

    def wait_busy(self, server, count):
        deadline = monotonic() + 3
        while monotonic() < deadline:
            if len(server._held) >= count:
                return
            sleep(0.01)
        self.fail(f"only {len(server._held)} of {count} workers became busy")


class BurstTests(LoadTestCase):
    def test_a_burst_is_turned_away_quickly_and_cleanly(self):
        server = self.serve(max_workers=4, reserved_for_voice=0)
        with ThreadPoolExecutor(max_workers=20) as pool:
            busy = [pool.submit(self.request) for _ in range(4)]
            self.wait_busy(server, 4)
            overflow = [future.result() for future in [pool.submit(self.request) for _ in range(16)]]
            self.assertEqual({status for status, _ in overflow}, {503})
            self.assertLess(max(seconds for _, seconds in overflow), 1.0)
            self.release.set()
            self.assertEqual({future.result()[0] for future in busy}, {200})
        self.assertEqual(self.request("GET", "/fast")[0], 200)  # recovered

    def test_voice_turns_get_the_reserved_workers_when_polling_fills_the_rest(self):
        server = self.serve(max_workers=4)  # one kept for voice
        with ThreadPoolExecutor(max_workers=8) as pool:
            polling = [pool.submit(self.request, "GET", "/api/status") for _ in range(3)]
            self.wait_busy(server, 3)
            self.assertEqual(self.request("GET", "/api/status")[0], 503)  # more polling is refused
            voice = pool.submit(self.request, "POST", "/api/assist")
            self.wait_busy(server, 4)  # ...but the voice turn got a worker
            self.assertEqual(self.request("POST", "/api/assist")[0], 503)  # and then everything is full
            self.release.set()
            self.assertEqual(voice.result()[0], 200)
            self.assertEqual({future.result()[0] for future in polling}, {200})

    def test_reservation_never_takes_every_worker(self):
        server = BoundedHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler, max_workers=1, reserved_for_voice=4)
        self.addCleanup(server.server_close)
        self.assertTrue(server._general.acquire(blocking=False))
        server._general.release()


class SlowClientTests(LoadTestCase):
    def test_a_dripping_client_cannot_stall_the_accept_loop(self):
        server = self.serve(max_workers=1, reserved_for_voice=0)
        with ThreadPoolExecutor(max_workers=2) as pool:
            busy = pool.submit(self.request)
            self.wait_busy(server, 1)
            drip = socket.create_connection(("127.0.0.1", self.port), timeout=5)
            self.addCleanup(drip.close)
            stop = Event()

            def dribble():
                try:
                    for _ in range(100):
                        if stop.is_set():
                            return
                        drip.sendall(b"G")
                        sleep(0.05)
                except OSError:
                    return
            Thread(target=dribble, daemon=True).start()
            sleep(0.1)
            self.release.set()
            self.assertEqual(busy.result()[0], 200)
            started = monotonic()
            status, _ = self.request("GET", "/fast")
            stop.set()
            self.assertEqual(status, 200)
            self.assertLess(monotonic() - started, 1.0)

    def test_drain_is_capped(self):
        self.assertLessEqual(http_server.DRAIN_SECONDS, 0.5)
        self.assertLessEqual(http_server.PEEK_SECONDS, 0.1)


if __name__ == "__main__":
    unittest.main()
