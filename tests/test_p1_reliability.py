"""Concurrency, delayed capture and bounded discovery regressions."""
import io
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from time import time
from unittest import TestCase
from unittest.mock import Mock, patch
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler

from arbitration import CaptureArbiter
from declan_ingress.http_server import BoundedHTTPServer
import ha_inventory
import music
import timers


class CaptureTests(TestCase):
    def test_delayed_plural_transcript_is_suppressed_without_waiting(self):
        arbiter = CaptureArbiter()
        capture = {'ended_at': time() - 4, 'duration': 2, 'rms': .3}
        with patch('arbitration.monotonic', side_effect=[10, 30]):
            self.assertTrue(arbiter.claim('turn on the light', 'kitchen', capture))
            self.assertFalse(arbiter.claim('Turn on the lights!', 'bedroom', capture))

    def test_opposites_repeats_and_distinct_speakers_are_separate(self):
        arbiter = CaptureArbiter()
        capture = {'ended_at': time() - 4, 'duration': 2, 'rms': .3}
        self.assertTrue(arbiter.claim('turn on lights', 'kitchen', capture, 'Jaco'))
        self.assertTrue(arbiter.claim('turn off lights', 'bedroom', capture, 'Jaco'))
        self.assertTrue(arbiter.claim('turn on lights', 'bedroom', capture, 'Edd'))
        self.assertTrue(arbiter.claim('turn on lights', 'kitchen', {**capture, 'ended_at': capture['ended_at'] + 3}))
        self.assertTrue(arbiter.claim('play city light', 'kitchen', capture))
        self.assertTrue(arbiter.claim('play city lights', 'bedroom', capture))


class InventoryTests(TestCase):
    def read(self, payloads):
        opener = Mock()
        opener.open.side_effect = [io.BytesIO(json.dumps(p).encode()) for p in payloads]
        return ha_inventory.read(('http://ha', {}, opener)), opener

    @staticmethod
    def row(i):
        return {'entity_id': f'light.test_{i}', 'state': 'on', 'attributes': {}}

    def test_pages_are_complete_and_requests_exclude_unrelated_attributes(self):
        rows = [self.row(i) for i in range(201)]
        (inventory, error), opener = self.read([{'total': 201, 'rows': rows[:200]}, {'total': 201, 'rows': rows[200:]}])
        self.assertIsNone(error)
        self.assertEqual(inventory, rows)
        self.assertEqual(opener.open.call_count, 2)
        for call in opener.open.call_args_list:
            request = call.args[0]
            self.assertEqual(request.full_url, 'http://ha/api/template')
            self.assertNotIn('attributes=entity.attributes', json.loads(request.data)['template'])

    def test_incomplete_duplicate_changed_and_malformed_pages_fail_closed(self):
        for pages in ([{'total': 2, 'rows': [self.row(0)]}],
                      [{'total': 2, 'rows': [self.row(0), self.row(0)]}],
                      [{'total': 1, 'rows': [{'entity_id': 'light.x', 'state': 'on', 'attributes': None}]}],
                      [{'total': -1, 'rows': []}], [[]]):
            self.assertEqual(self.read(pages)[0], (None, 'unavailable'))
        rows = [self.row(i) for i in range(200)]
        self.assertEqual(self.read([{'total': 201, 'rows': rows}, {'total': 202, 'rows': [self.row(200)]}])[0],
                         (None, 'unavailable'))

    def test_oversized_and_slow_pages_are_rejected(self):
        opener = Mock()
        opener.open.return_value = io.BytesIO(b'x' * (ha_inventory.MAX_PAGE_BYTES + 1))
        self.assertEqual(ha_inventory.read(('http://ha', {}, opener)), (None, 'unavailable'))
        with patch.object(ha_inventory, 'monotonic', side_effect=[0, 11]):
            self.assertEqual(ha_inventory.read(('http://ha', {}, opener)), (None, 'unavailable'))

    def test_template_renders_native_datetime_without_serializing_it(self):
        from datetime import datetime
        from types import SimpleNamespace
        from jinja2.sandbox import SandboxedEnvironment
        entity = SimpleNamespace(entity_id='media_player.test', domain='media_player', state='playing',
                                 attributes={'friendly_name': 'Test', 'last_seen': datetime.now(),
                                             'group_members': ['media_player.test']})
        opener = Mock()
        def render(request, timeout):
            template = json.loads(request.data)['template']
            env = SandboxedEnvironment()
            env.filters['to_json'] = json.dumps
            value = env.from_string(template).render(states=[entity], integration_entities=lambda _: ['media_player.test'],
                                                    area_name=lambda _: 'Study', device_id=lambda _: 'device')
            return io.BytesIO(value.encode())
        opener.open.side_effect = render
        rows, error = ha_inventory.read(('http://ha', {}, opener), music=True)
        self.assertIsNone(error)
        self.assertEqual(rows[0]['attributes'], {'friendly_name': 'Test', 'group_members': ['media_player.test']})
        self.assertTrue(rows[0]['declan_music_assistant'])


class WorkerTests(TestCase):
    def test_handler_failure_releases_worker_slot(self):
        from http.server import ThreadingHTTPServer
        with BoundedHTTPServer(('127.0.0.1', 0), BaseHTTPRequestHandler, max_workers=1) as server:
            self.assertTrue(server._slots.acquire(blocking=False))
            with patch.object(ThreadingHTTPServer, 'process_request_thread', side_effect=RuntimeError):
                with self.assertRaises(RuntimeError):
                    server.process_request_thread(Mock(), ('127.0.0.1', 123))
            self.assertTrue(server._slots.acquire(blocking=False))
            server._slots.release()

    def test_overload_returns_503_then_recovers_after_worker_finishes(self):
        entered, release = Event(), Event()
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                entered.set()
                release.wait(3)
                self.send_response(200)
                self.send_header('Content-Length', '0')
                self.end_headers()
            def log_message(self, *args):
                pass
        with BoundedHTTPServer(('127.0.0.1', 0), Handler, max_workers=1) as server:
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                first = HTTPConnection('127.0.0.1', server.server_port, timeout=4)
                self.addCleanup(first.close)
                first.request('GET', '/')
                self.assertTrue(entered.wait(2))
                other = HTTPConnection('127.0.0.1', server.server_port, timeout=4)
                self.addCleanup(other.close)
                other.request('GET', '/')
                self.assertEqual(other.getresponse().status, 503)
                release.set()
                self.assertEqual(first.getresponse().status, 200)
                self.assertTrue(server._slots.acquire(timeout=2))
                server._slots.release()
                third = HTTPConnection('127.0.0.1', server.server_port, timeout=4)
                self.addCleanup(third.close)
                third.request('GET', '/')
                self.assertEqual(third.getresponse().status, 200)
            finally:
                release.set()
                server.shutdown()
                worker.join()


class SharedStateTests(TestCase):
    def test_old_unauthorized_search_does_not_discard_a_new_token(self):
        from urllib.error import HTTPError
        opener = Mock()
        def search(request, timeout):
            with music.SPOTIFY_TOKEN_LOCK:
                music.spotify_token = (('id','secret'), 'new-token', float('inf'))
            raise HTTPError(request.full_url, 401, 'Expired', {}, None)
        opener.open.side_effect = search
        with patch.object(music, 'spotify_token', (('id','secret'), 'old-token', float('inf'))), patch.object(
                music, 'spotify_credentials', return_value=(('id','secret'), 'test')):
            with self.assertRaises(HTTPError):
                music.spotify_search(opener, 'test', '', ('track',))
            self.assertEqual(music.spotify_token[1], 'new-token')

    def test_simultaneous_spotify_searches_share_one_token_refresh(self):
        calls = []
        def open_request(request, timeout):
            calls.append(request)
            if '/api/token' in request.full_url:
                return io.BytesIO(b'{"access_token":"token","expires_in":3600}')
            return io.BytesIO(b'{"tracks":{"items":[]}}')
        opener = Mock()
        opener.open.side_effect = open_request
        with patch.object(music, 'spotify_token', None), patch.object(music, 'spotify_credentials', return_value=(('id','secret'), 'test')):
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda _: music.spotify_search(opener, 'test', '', ('track',)), range(8)))
        self.assertEqual(sum('/api/token' in call.full_url for call in calls), 1)

    def test_spotify_market_and_quoted_search_fields(self):
        from urllib.parse import parse_qs, urlsplit
        opener = Mock()
        opener.open.return_value = io.BytesIO(b'{}')
        with patch.object(music, 'spotify_token', (('id','secret'), 'token', float('inf'))), patch.object(
                music, 'spotify_credentials', return_value=(('id','secret'), 'test')), patch.dict(music.os.environ, {'DECLAN_SPOTIFY_MARKET':'za'}):
            music.spotify_search(opener, 'Say "hello"', 'A\\B "artist"', ('track',))
        query = parse_qs(urlsplit(opener.open.call_args.args[0].full_url).query)
        self.assertEqual(query['market'], ['ZA'])
        self.assertEqual(query['q'], ['track:"Say \\"hello\\"" artist:"A\\\\B \\"artist\\""'])

    def test_idle_timer_poll_reads_without_write_lock(self):
        path = Path(self.enterContext(TemporaryDirectory())) / 'timers.sqlite3'
        self.enterContext(patch.object(timers, 'DATABASE', path))
        timers.initialize()
        with closing(sqlite3.connect(path)) as writer:
            writer.execute('BEGIN IMMEDIATE')
            timers.ring_due(Mock())
            writer.rollback()

    def test_concurrent_timer_pollers_claim_each_alarm_once(self):
        path = Path(self.enterContext(TemporaryDirectory())) / 'timers.sqlite3'
        self.enterContext(patch.object(timers, 'DATABASE', path))
        with timers.database() as db:
            db.execute("INSERT INTO timers(name,satellite,room,deadline,next_alarm) VALUES ('Tea','assist_satellite.kitchen','Kitchen',0,0)")
        with patch.object(timers, 'ha_json') as announce:
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda _: timers.ring_due(Mock()), range(4)))
        announce.assert_called_once()
