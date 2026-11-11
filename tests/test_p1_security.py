"""Exercise HTTP policies and privacy controls without live household access."""
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from threading import Thread
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import urlsplit

from declan_ingress import proxy
from declan_ingress.security import BadTokenLimiter
import history
import server


class LimiterTests(TestCase):
    def test_window_recovery_valid_reset_and_capacity(self):
        now = [10]
        limiter = BadTokenLimiter(limit=2, capacity=2, clock=lambda: now[0])
        self.assertEqual(limiter.check('a', False), 0)
        self.assertEqual(limiter.check('a', True), 0)
        self.assertFalse(limiter.failures)
        limiter.check('a', False)
        limiter.check('a', False)
        self.assertEqual(limiter.check('a', True), 60)
        now[0] = 69.5
        self.assertEqual(limiter.check('a', False), 1)
        limiter.check('b', False)
        self.assertEqual(limiter.check('c', False), 1)
        self.assertEqual(len(limiter.failures), 2)
        self.assertEqual(limiter.check('c', True), 0)
        now[0] = 70
        self.assertEqual(limiter.check('a', True), 0)
        self.assertNotIn('a', limiter.failures)
        self.assertIn('b', limiter.failures)

    def test_concurrent_failures_cannot_exceed_budget(self):
        limiter = BadTokenLimiter(clock=lambda: 100)
        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(lambda _: limiter.check('ha', False), range(40)))
        self.assertEqual(results.count(0), 10)
        self.assertEqual(results.count(60), 30)
        self.assertEqual(limiter.failures['ha'][1], 10)


class HTTPPolicyTests(TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            'DECLAN_ASSIST_TOKEN': 'bridge-secret', 'DECLAN_INGRESS_TOKEN': 'i' * 64,
        }))
        self.http = self.start(server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler))
        self.now = [100]
        self.http.bad_tokens = BadTokenLimiter(limit=2, clock=lambda: self.now[0])

    def start(self, http):
        self.enterContext(http)
        worker = Thread(target=http.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(worker.join)
        self.addCleanup(http.shutdown)
        return http

    def request(self, path='/', *, http=None, token=None, extra=None, method='GET', body=None):
        http = http or self.http
        headers = dict(extra or {})
        if token is not None:
            headers['Authorization'] = 'Bearer ' + token
        if body is not None:
            headers['Content-Type'] = 'application/json'
        connection = HTTPConnection(*http.server_address, timeout=4)
        try:
            connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def check_page(self, response, *, ingress, scripts):
        status, headers, page = response
        self.assertEqual(status, 200)
        self.assertEqual(int(headers['Content-Length']), len(page))
        nonces = re.findall(br'<script nonce="([^"]+)"', page)
        self.assertEqual(len(nonces), scripts)
        self.assertEqual(len(set(nonces)), 1)
        csp = headers['Content-Security-Policy']
        self.assertIn("script-src 'nonce-" + nonces[0].decode() + "'", csp)
        self.assertNotIn("script-src 'unsafe-inline'", csp)
        self.assertIn("frame-ancestors " + ("'self'" if ingress else "'none'"), csp)
        self.assertEqual(headers['X-Frame-Options'], 'SAMEORIGIN' if ingress else 'DENY')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(headers['Referrer-Policy'], 'no-referrer')
        self.assertIn('microphone=(self)', headers['Permissions-Policy'])
        self.assertIn("media-src 'self' blob:", csp)
        return nonces[0]

    def test_direct_and_ingress_pages_use_fresh_matching_nonces(self):
        first = self.check_page(self.request(), ingress=False, scripts=1)
        second = self.check_page(self.request(), ingress=False, scripts=1)
        self.assertNotEqual(first, second)
        self.check_page(self.request(extra={'X-Declan-Ingress-Token': 'i' * 64}), ingress=True, scripts=1)
        # The proxy adds a second script and must nonce both after insertion.
        self.enterContext(patch.object(proxy, 'SUPERVISOR_ADDRESS', '127.0.0.1'))
        gateway = self.start(proxy.ThreadingHTTPServer(('127.0.0.1', 0), proxy.ProxyHandler))
        gateway.target = urlsplit('http://127.0.0.1:' + str(self.http.server_port))
        gateway.ingress_token = 'i' * 64
        gateway.panel_token = 'panel-secret'
        self.check_page(self.request(http=gateway), ingress=True, scripts=2)
        status, headers, _ = self.request('/missing', http=gateway)
        self.assertEqual(status, 404)
        self.assertIn("script-src 'none'", headers['Content-Security-Policy'])
        self.assertEqual(headers['X-Frame-Options'], 'SAMEORIGIN')

    def test_auth_failures_share_endpoint_budget_and_ignore_forwarded_peer(self):
        for path in ('/api/assist', '/api/assist/history'):
            status, headers, _ = self.request(path, method='POST', token='wrong',
                extra={'X-Forwarded-For': path, 'X-Real-IP': '192.0.2.5'})
            self.assertEqual(status, 401)
            self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        with patch.object(server, 'converse') as converse:
            status, headers, _ = self.request('/api/assist', method='POST', token='bridge-secret')
            self.assertEqual(status, 429)
            self.assertEqual(headers['Retry-After'], '60')
            converse.assert_not_called()
        # Health is unaffected, and valid auth resumes at the original deadline.
        self.assertEqual(self.request('/health')[0], 200)
        self.now[0] = 160
        status, headers, _ = self.request('/api/assist', method='POST', token='bridge-secret', body={})
        self.assertEqual(status, 400)
        self.assertNotIn('Retry-After', headers)


class RetentionTests(TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.object(history, 'DATABASE', Path(directory) / 'history.sqlite3'))
        self.enterContext(patch.dict(os.environ, {'DECLAN_HISTORY_RETENTION_DAYS': '7'}))

    def test_config_validation(self):
        for value in ('0', '31', '-1', '1.5', '', ' 7', '07'):
            with self.subTest(value=value), patch.dict(os.environ, {'DECLAN_HISTORY_RETENTION_DAYS': value}):
                with self.assertRaises(ValueError):
                    history.retention_seconds()
        self.assertEqual(history.retention_seconds(), 7 * 86400)
        with patch.dict(os.environ, {'DECLAN_HISTORY_RETENTION_DAYS': '1'}):
            self.assertEqual(history.retention_seconds(), 86400)
        with patch.dict(os.environ, {'DECLAN_HISTORY_RETENTION_DAYS': '30'}):
            self.assertEqual(history.retention_seconds(), 30 * 86400)

    def test_read_filter_pagination_export_and_prune_preserve_learning(self):
        now = 2_000_000
        with patch.object(history, 'time', return_value=now - 7 * 86400 - 1):
            history.record('old', 'assist', 'old private words', 'old reply', speaker={'name': 'Jaco', 'confidence': .9})
        with patch.object(history, 'time', return_value=now - 7 * 86400):
            history.record('boundary', 'assist', 'boundary', 'reply')
        with patch.object(history, 'time', return_value=now):
            history.record('new', 'assist', 'new', 'reply')
            with history.database() as db:
                db.execute("INSERT INTO learned_intents VALUES ('alias', 'good morning')")
            self.assertEqual([turn['session_id'] for turn in history.recent(limit=None)], ['new', 'boundary'])
            self.assertEqual([turn['session_id'] for turn in history.recent(before=3)], ['boundary'])
            with history.database() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM turns').fetchone()[0], 3)
            history.prune()
            with history.database() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM turns').fetchone()[0], 2)
            self.assertEqual(history.learned_intent('alias'), 'good morning')
