"""Reject hostile string subclasses at the chat recall privacy boundary."""
import unittest

from declan.turn.chat_recall_privacy import safe_chat_text


class ChatRecallStringBoundaryTests(unittest.TestCase):
    def test_plain_text_still_accepted(self):
        self.assertEqual(safe_chat_text("hello there"), "hello there")

    def test_hostile_subclass_is_not_inspected(self):
        class HostileText(str):
            def strip(self, chars: str | None = None) -> str:
                raise RuntimeError("unexpected strip")
        self.assertIsNone(safe_chat_text(HostileText("hello")))


if __name__ == "__main__":
    unittest.main()
