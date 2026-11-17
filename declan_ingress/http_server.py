"""Bound request workers and reject overload without creating extra threads."""
from http.server import ThreadingHTTPServer
from threading import BoundedSemaphore
if __package__:
    from .security import BadTokenLimiter
else:
    from security import BadTokenLimiter  # type: ignore[no-redef]


class BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, *args, max_workers=16, **kwargs):
        self._slots = BoundedSemaphore(max_workers)
        self.bad_tokens = BadTokenLimiter()
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            try:
                # Drain the already-sent HTTP request before closing. Windows can
                # reset the peer connection if unread request bytes remain.
                request.settimeout(0.2)
                received = bytearray()
                while b"\r\n\r\n" not in received and len(received) < 8192:
                    chunk = request.recv(min(2048, 8192 - len(received)))
                    if not chunk:
                        break
                    received.extend(chunk)
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nRetry-After: 1\r\n"
                                b"Connection: close\r\nContent-Length: 0\r\n\r\n")
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

