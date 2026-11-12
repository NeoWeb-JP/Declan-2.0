import io
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread
from unittest import TestCase, mock
from urllib.parse import urlsplit

from declan_ingress import proxy


class IngressTests(TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), proxy.ProxyHandler)
        self.server.panel_token = 'panel-secret'
        self.server.ingress_token = 'upstream-secret'
        self.server.target = urlsplit('http://declan.invalid:80')
        self.thread = Thread(target=self.server.serve_forever)
        self.thread.start()
        self.addCleanup(self.stop)
        self.upstream = mock.Mock()
        self.response = self.upstream.getresponse.return_value
        self.response.status = 200
        self.response.getheader.side_effect = lambda name, default=None: {'Content-Type': 'text/html', 'Content-Length': '13'}.get(name, default)
        self.response.read.side_effect = [b'<html></html>', b'']

    def stop(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def request(self, method='POST', headers=None, supervisor=True, path=None):
        connection = HTTPConnection(*self.server.server_address)
        with mock.patch.object(proxy, 'SUPERVISOR_ADDRESS', '127.0.0.1' if supervisor else '192.0.2.1'), mock.patch.object(proxy, 'HTTPConnection', return_value=self.upstream):
            connection.request(method, path or ('/' if method == 'GET' else '/api/updates'), body='{}' if method == 'POST' else None, headers=headers or {})
            response = connection.getresponse()
            result = response.status, response.read()
        connection.close()
        return result

    def test_http_panel_token_fallback(self):
        self.assertEqual(self.request(headers={'Content-Type': 'application/json', 'X-Declan-Panel-Token': 'panel-secret'})[0], 200)
        self.assertEqual(self.upstream.request.call_args.args[3], {'X-Declan-Ingress-Token': 'upstream-secret', 'Content-Type': 'application/json'})

    def test_missing_and_invalid_tokens_rejected(self):
        for token in ['', 'wrong']:
            self.assertEqual(self.request(headers={'X-Declan-Panel-Token': token})[0], 403)
        self.upstream.request.assert_not_called()

    def test_cross_site_rejected_even_with_token(self):
        for site in ['cross-site', 'same-site', 'none', '']:
            self.assertEqual(self.request(headers={'Sec-Fetch-Site': site, 'X-Declan-Panel-Token': 'panel-secret'})[0], 403)
        self.upstream.request.assert_not_called()

    def test_supervisor_check_remains_required(self):
        self.assertEqual(self.request(headers={'X-Declan-Panel-Token': 'panel-secret'}, supervisor=False)[0], 403)

    def test_same_origin_and_content_type(self):
        self.assertEqual(self.request(headers={'Sec-Fetch-Site': 'same-origin', 'Content-Type': 'application/json'})[0], 200)
        self.assertEqual(self.request(headers={'X-Declan-Panel-Token': 'panel-secret', 'Content-Type': 'text/plain'})[0], 415)

    def test_page_delivers_only_panel_secret(self):
        status, body = self.request(method='GET')
        self.assertEqual(status, 200)
        self.assertIn(b'panel-secret', body)
        self.assertNotIn(b'upstream-secret', body)
        self.assertTrue(body.startswith(b'<html><script>'))
        self.assertTrue(body.endswith(b'</html>'))

    def test_voicepipeline_management_route_is_allowed_with_same_panel_boundary(self):
        self.response.getheader.side_effect = lambda name, default=None: {'Content-Type': 'application/json', 'Content-Length': '2'}.get(name, default)
        for method in ('GET', 'POST'):
            # Each upstream response needs its own stream: the client can finish
            # reading Content-Length before the previous proxy thread reads EOF.
            response = mock.Mock()
            response.status = 200
            response.getheader.side_effect = self.response.getheader.side_effect
            response.read.side_effect = io.BytesIO(b'{}').read
            self.upstream.getresponse.return_value = response
            headers = {'Content-Type': 'application/json', 'X-Declan-Panel-Token': 'panel-secret'}
            self.assertEqual(self.request(method=method, headers=headers, path='/api/voicepipeline')[0], 200)
        self.assertEqual(self.request(path='/api/voicepipeline')[0], 403)
