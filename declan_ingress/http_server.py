"""Bound request workers and reject overload without creating extra threads.

FUT-64 (#834): under load, extra requests are turned away quickly and
cleanly instead of hanging voice commands.

- At most ``max_workers`` requests run at once. A quarter of them (4 of 16)
  are kept for voice turns (POST /api/assist, /api/chat, /api/stt, /api/tts),
  so the panel polling or a burst of settings requests can't starve a
  satellite's command.
- Up to 64 connections queue for the accept loop (socketserver's default of
  5 made a burst wait a second for the client to retry).
- A request that doesn't fit gets an immediate ``503 Retry-After: 1``. Reading
  what the client already sent before closing is capped at a quarter of a
  second in total, so a slow or stalled client can't hold up the accept loop.
"""
import socket
from http.server import ThreadingHTTPServer
from threading import BoundedSemaphore, Lock
from time import monotonic

if __package__:
    from .security import BadTokenLimiter
else:
    from security import BadTokenLimiter  # type: ignore[no-redef,import-not-found]

VOICE_REQUESTS = (b"POST /api/assist ", b"POST /api/assist?", b"POST /api/chat ", b"POST /api/chat?",
                  b"POST /api/stt ", b"POST /api/stt?", b"POST /api/tts ", b"POST /api/tts?")
PEEK_SECONDS = 0.05
DRAIN_SECONDS = 0.25


class BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    # socketserver's default backlog of 5 drops connections in a burst, and the
    # client only retries after a second; queue them so they're answered (or
    # turned away) straight away.
    request_queue_size = 64

    def __init__(self, *args, max_workers=16, reserved_for_voice=None, **kwargs):
        reserved = max_workers // 4 if reserved_for_voice is None else reserved_for_voice
        reserved = max(0, min(reserved, max_workers - 1))
        self._slots = BoundedSemaphore(max_workers)
        self._general = BoundedSemaphore(max_workers - reserved)
        self._held: dict[int, bool] = {}
        self._held_lock = Lock()
        self.bad_tokens = BadTokenLimiter()
        super().__init__(*args, **kwargs)

    @staticmethod
    def _is_voice(request):
        """Peek at the request line without consuming it; unknown counts as not voice."""
        try:
            previous = request.gettimeout()
            request.settimeout(PEEK_SECONDS)
            try:
                head = request.recv(32, socket.MSG_PEEK)
            finally:
                request.settimeout(previous)
        except (OSError, ValueError, AttributeError):
            return False
        return isinstance(head, bytes) and head.startswith(VOICE_REQUESTS)

    def _acquire(self, request):
        """True with a slot taken; voice turns may also use the reserved slots."""
        voice = self._is_voice(request)
        general = False
        if not voice:
            if not self._general.acquire(blocking=False):
                return False
            general = True
        if not self._slots.acquire(blocking=False):
            if general:
                self._general.release()
            return False
        with self._held_lock:
            self._held[id(request)] = general
        return True

    def _release(self, request):
        with self._held_lock:
            general = self._held.pop(id(request), False)
        if general:
            self._general.release()
        self._slots.release()

    def _reject(self, request):
        try:
            # Drain the already-sent HTTP request before closing (Windows can
            # reset the peer if unread bytes remain), but never for long.
            deadline = monotonic() + DRAIN_SECONDS
            received = bytearray()
            while b"\r\n\r\n" not in received and len(received) < 8192:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    break
                request.settimeout(remaining)
                chunk = request.recv(min(2048, 8192 - len(received)))
                if not chunk:
                    break
                received.extend(chunk)
            request.settimeout(DRAIN_SECONDS)
            request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nRetry-After: 1\r\n"
                            b"Connection: close\r\nContent-Length: 0\r\n\r\n")
        except OSError:
            pass
        finally:
            self.shutdown_request(request)

    def process_request(self, request, client_address):
        if not self._acquire(request):
            self._reject(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._release(request)
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._release(request)
