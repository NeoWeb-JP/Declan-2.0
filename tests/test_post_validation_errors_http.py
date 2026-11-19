"""POST malformed payload response contract regressions."""

import unittest
from unittest.mock import Mock

from declan.http.post_validation_errors_http import send_validation_error, validation_error_message


class PostValidationErrorTests(unittest.TestCase):
    def test_route_specific_messages(self):
        cases = {
            "/api/settings/spotify": "Send valid Spotify settings.",
            "/api/history/clear": "Send valid history confirmation.",
            "/api/chat": "Send a message of 1 to 1,000 characters.",
            "/api/assist": "Send a message of 1 to 1,000 characters.",
            "/api/tts": "Send a message of 1 to 1,000 characters.",
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(validation_error_message(path), expected)
                handler = Mock(path=path)
                send_validation_error(handler)
                handler.send_json.assert_called_once_with(400, {"error": expected})


if __name__ == "__main__":
    unittest.main()
