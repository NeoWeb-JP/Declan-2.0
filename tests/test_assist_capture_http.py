"""Capture arbitration HTTP contract regression tests."""

import unittest
from unittest.mock import Mock

import assist_capture_http as capture


class AssistCaptureHttpTests(unittest.TestCase):
    def test_confident_speaker(self):
        self.assertEqual(capture.trusted_speaker_name({"name": "Jaco", "confidence": 0.85}), "Jaco")

    def test_low_confidence_and_invalid_speakers(self):
        for value in (None, {}, {"name": "Jaco", "confidence": 0.84},
                      {"name": "Jaco", "confidence": True},
                      {"name": 123, "confidence": 0.99}):
            with self.subTest(value=value):
                self.assertIsNone(capture.trusted_speaker_name(value))

    def invoke(self, *, source="assist", claim=True, session_id="existing"):
        handler, arbiter, normalize, new_id = Mock(), Mock(), Mock(return_value="normalized"), Mock(return_value="new")
        arbiter.claim.return_value = claim
        result = capture.suppress_duplicate(
            handler, source=source, body={"speaker": {"name": "Edd", "confidence": 0.9}, "capture": {"id": "1"}},
            message="Lights", session_id=session_id, satellite="kitchen",
            origin_device="bedroom", arbiter=arbiter, normalize=normalize, new_session_id=new_id,
        )
        return result, handler, arbiter, new_id

    def test_claimed_assist_is_not_suppressed(self):
        result, handler, arbiter, _ = self.invoke()
        self.assertFalse(result)
        arbiter.claim.assert_called_once_with("normalized", "kitchen", {"id": "1"}, "Edd")
        handler.send_json.assert_not_called()

    def test_duplicate_returns_empty_reply(self):
        result, handler, _, new_id = self.invoke(claim=False)
        self.assertTrue(result)
        handler.send_json.assert_called_once_with(
            200, {"reply": "", "session_id": "existing", "outcome": "duplicate"},
        )
        new_id.assert_not_called()

    def test_duplicate_allocates_missing_session(self):
        result, handler, _, new_id = self.invoke(claim=False, session_id=None)
        self.assertTrue(result)
        new_id.assert_called_once_with(24)
        handler.send_json.assert_called_once_with(
            200, {"reply": "", "session_id": "new", "outcome": "duplicate"},
        )

    def test_non_assist_bypasses_arbiter(self):
        result, handler, arbiter, _ = self.invoke(source="chat")
        self.assertFalse(result)
        arbiter.claim.assert_not_called()
        handler.send_json.assert_not_called()


if __name__ == "__main__":
    unittest.main()
