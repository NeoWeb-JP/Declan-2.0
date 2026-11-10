"""Send a short browser recording to the Home Assistant Assist STT stage."""

import json
import re
from time import monotonic
from urllib.parse import urlsplit, urlunsplit


MAX_AUDIO_BYTES = 20 * 16000 * 2


class AssistSpeechError(ValueError):
    def __init__(self, code):
        self.code = code if isinstance(code, str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", code) else "unknown"
        super().__init__(self.code)


def transcribe(url, token, audio, *, pipeline=None):
    import websocket

    address = urlsplit(url)
    endpoint = urlunsplit(("wss" if address.scheme == "https" else "ws", address.netloc,
                           address.path + "/api/websocket", "", ""))
    try:
        socket = websocket.create_connection(endpoint, timeout=5, redirect_limit=0)
        try:
            return run_stt(socket, token, audio, pipeline)
        finally:
            socket.close(timeout=0)
    except websocket.WebSocketException as error:
        raise OSError("Assist connection failed") from error


def run_stt(socket, token, audio, pipeline):
    deadline = monotonic() + 25

    def receive():
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("Assist transcription timed out")
        socket.settimeout(remaining)
        message = json.loads(socket.recv())
        if not isinstance(message, dict):
            raise ValueError("Invalid Assist message")
        return message

    if receive().get("type") != "auth_required":
        raise ValueError("Home Assistant did not request authentication")
    socket.send(json.dumps({"type": "auth", "access_token": token}))
    if receive().get("type") != "auth_ok":
        raise AssistSpeechError("auth-rejected")
    run = {"id": 1, "type": "assist_pipeline/run", "start_stage": "stt", "end_stage": "stt",
           "input": {"sample_rate": 16000}, "timeout": 20}
    if pipeline:
        run["pipeline"] = pipeline
    socket.send(json.dumps(run))
    handler = None
    while True:
        message = receive()
        if message.get("id") != 1:
            continue
        if message.get("type") == "result" and not message.get("success"):
            raise AssistSpeechError((message.get("error") or {}).get("code"))
        event = message.get("event") or {}
        kind, data = event.get("type"), event.get("data") or {}
        if kind == "run-start":
            handler = (data.get("runner_data") or {}).get("stt_binary_handler_id")
        elif kind == "stt-start":
            if type(handler) is not int or not 0 <= handler <= 255:
                raise ValueError("Home Assistant did not provide an audio channel")
            prefix = bytes([handler])
            for offset in range(0, len(audio), 4096):
                socket.send_binary(prefix + audio[offset:offset + 4096])
            socket.send_binary(prefix)
        elif kind == "stt-end":
            text = (data.get("stt_output") or {}).get("text")
            return text.strip() if isinstance(text, str) else ""
        elif kind == "error":
            raise AssistSpeechError(data.get("code"))
        elif kind == "run-end":
            return ""
