"""POST content-type gate regression tests."""

import unittest
from email.message import Message
from unittest.mock import Mock

from declan.http.post_content_type_http import enforce_json_content_type


class PostContentTypeTests(unittest.TestCase):
    def handler(self, content_type):
        headers = Message()
        headers["Content-Type"] = content_type
        handler = Mock()
        handler.headers = headers
        return handler

    def test_accepts_json_with_optional_parameters(self):
        for mime in ("application/json", "application/json; charset=utf-8"):
            with self.subTest(mime=mime):
                handler = self.handler(mime)
                self.assertTrue(enforce_json_content_type(handler))
                handler.send_json.assert_not_called()

    def test_rejects_other_content_types(self):
        for mime in ("text/plain", "application/x-www-form-urlencoded", "application/json-seq", "multipart/form-data"):
            with self.subTest(mime=mime):
                handler = self.handler(mime)
                self.assertFalse(enforce_json_content_type(handler))
                handler.send_json.assert_called_once_with(415, {"error": "Send application/json."})

    def test_rejects_missing_content_type(self):
        handler = Mock()
        handler.headers = Message()
        self.assertFalse(enforce_json_content_type(handler))
        handler.send_json.assert_called_once_with(415, {"error": "Send application/json."})


if __name__ == "__main__":
    unittest.main()
