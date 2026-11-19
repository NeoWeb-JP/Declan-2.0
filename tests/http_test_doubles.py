"""Readable, closeable HTTP responses for in-memory provider tests."""
from email.message import Message
from io import BytesIO


class HTTPResponse(BytesIO):
    status: int = 200
    headers: Message | dict[str, str]

    def __init__(self, body=b''):
        super().__init__(body)
        self.headers = Message()
