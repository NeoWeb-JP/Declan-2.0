"""HTTP response policy and bounded, per-peer bad-credential throttling."""
from collections import OrderedDict
import math
import re
import secrets
from threading import Lock
from time import monotonic


def secure_page(page):
    nonce = secrets.token_urlsafe(24)
    def with_nonce(match):
        # A proxied page already has the standalone server's nonce. Replace it.
        tag = re.sub(br'\snonce=(?:"[^"]*"|\x27[^\x27]*\x27)', b'', match[0], flags=re.I)
        return tag[:-1] + b' nonce="' + nonce.encode() + b'">'
    return re.sub(br'<script(?=[\s>])[^>]*>', with_nonce, page, flags=re.I), nonce


def response_headers(*, ingress=False, nonce=None):
    script = "'nonce-" + nonce + "'" if nonce else "'none'"
    ancestors = "'self'" if ingress else "'none'"
    return {
        'Content-Security-Policy': (
            "default-src 'none'; script-src " + script + "; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; media-src 'self' blob:; "
            "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors " + ancestors
        ),
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'SAMEORIGIN' if ingress else 'DENY',
        'Referrer-Policy': 'no-referrer',
        'Permissions-Policy': 'camera=(), microphone=(self), geolocation=()',
    }


class BadTokenLimiter:
    """Ten failures exhaust a socket peer's fixed sixty-second window.

    Never trust forwarding headers or store submitted credentials. The fixed
    capacity also bounds memory when many different peers submit bad tokens.
    """

    def __init__(self, *, limit=10, window=60, capacity=4096, clock=monotonic):
        self.limit, self.window, self.capacity = limit, window, capacity
        self.clock = clock
        self.failures = OrderedDict()
        self.lock = Lock()

    def check(self, peer, valid):
        with self.lock:
            now = self.clock()
            # Entries are ordered by fixed window expiry; retries never extend it.
            while self.failures and next(iter(self.failures.values()))[0] <= now:
                self.failures.popitem(last=False)
            entry = self.failures.get(peer)
            if entry and entry[1] >= self.limit:
                return max(1, math.ceil(entry[0] - now))
            if valid:
                self.failures.pop(peer, None)
                return 0
            if entry:
                self.failures[peer] = (entry[0], entry[1] + 1)
            elif len(self.failures) < self.capacity:
                self.failures[peer] = (now + self.window, 1)
            else:
                return max(1, math.ceil(next(iter(self.failures.values()))[0] - now))
            return 0
