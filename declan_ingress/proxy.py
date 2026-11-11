"""Forward Home Assistant Ingress requests to the authenticated Declan web API."""

from http.client import HTTPConnection, HTTPSConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


GET_PATHS = {
    "/", "/logo.png", "/api/ha-status", "/api/history", "/api/history/export",
    "/api/settings/export", "/api/settings/export-learning", "/api/settings/recovery", "/api/settings/recovery-learning", "/api/voice-profiles", "/api/diagnostics", "/api/settings/spotify", "/api/updates", "/api/updates/status",
}
POST_PATHS = {
    "/api/chat", "/api/tts", "/api/stt", "/api/history/clear",
    "/api/voice-profiles", "/api/settings/import", "/api/history/intents", "/api/settings/spotify", "/api/updates",
}
SUPERVISOR_ADDRESS = "172.30.32.2"


class ProxyHandler(BaseHTTPRequestHandler):
    timeout = 10

    def log_message(self, *args):
        # Ingress paths and headers can contain credentials.
        pass

    def send_error_json(self, status, message):
        body = json.dumps({"error": message}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def forward(self):
        if self.client_address[0] != SUPERVISOR_ADDRESS:
            self.send_error_json(403, "Open Declan from Home Assistant.")
            return

        path, _, query = self.path.partition("?")
        allowed = POST_PATHS if self.command == "POST" else GET_PATHS
        if path not in allowed or (query and path != "/api/history"):
            self.send_error_json(404, "Not found.")
            return

        body = None
        headers = {"X-Declan-Ingress-Token": self.server.ingress_token}
        if self.command == "POST":
            if self.headers.get("Sec-Fetch-Site") != "same-origin":
                self.send_error_json(403, "Send requests from the Declan panel.")
                return
            expected = "application/octet-stream" if path == "/api/stt" else "application/json"
            if self.headers.get_content_type() != expected or self.headers.get("Transfer-Encoding"):
                self.send_error_json(415, f"Send {expected}.")
                return
            limit = 450000 if path == "/api/voice-profiles" else 640_000 if path == "/api/stt" else 196608 if path == "/api/settings/import" else 8192
            length = self.headers.get("Content-Length", "")
            if len(length) > 7 or not length.isascii() or not length.isdigit() or not 0 < int(length) <= limit:
                self.send_error_json(400, "Invalid request size.")
                return
            try:
                body = self.rfile.read(int(length))
            except OSError:
                self.send_error_json(408, "Could not read the request.")
                return
            if len(body) != int(length):
                self.send_error_json(400, "Incomplete request.")
                return
            headers["Content-Type"] = expected

        target = self.server.target
        connection_type = HTTPSConnection if target.scheme == "https" else HTTPConnection
        upstream = connection_type(target.hostname, target.port, timeout=85)
        try:
            upstream.request(self.command, self.path, body, headers)
            response = upstream.getresponse()
        except (HTTPException, OSError, ValueError):
            upstream.close()
            self.send_error_json(502, "Could not reach the Declan server.")
            return

        try:
            self.send_response(response.status)
            for name in ("Content-Type", "Content-Disposition", "Content-Length"):
                value = response.getheader(name)
                if value is not None:
                    self.send_header(name, value)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            while chunk := response.read(65536):
                self.wfile.write(chunk)
        except (HTTPException, OSError):
            self.close_connection = True
        finally:
            upstream.close()

    do_GET = forward
    do_POST = forward


def main():
    options = json.loads(Path("/data/options.json").read_text(encoding="utf-8"))
    target = urlsplit(options["declan_url"])
    token = options["ingress_token"]
    if (target.scheme not in {"http", "https"} or not target.hostname
            or target.path not in {"", "/"} or any((target.username, target.password, target.query, target.fragment))):
        raise SystemExit("Set the Declan server URL to an HTTP or HTTPS origin.")
    if len(token) < 32 or not token.isascii() or not token.isalnum():
        raise SystemExit("Set a separate alphanumeric ingress token of at least 32 characters.")
    # Supervisor writes options.json as root with mode 0600.
    if os.getuid() == 0:
        os.setgroups([])
        os.setgid(65534)
        os.setuid(65534)
    with ThreadingHTTPServer(("0.0.0.0", 8099), ProxyHandler) as server:
        server.target = target
        server.ingress_token = token
        server.serve_forever()


if __name__ == "__main__":
    main()
