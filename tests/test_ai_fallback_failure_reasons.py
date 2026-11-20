"""AI fallback failures say why nothing changed, and log the reason (no secrets)."""
import sqlite3
import unittest

from declan.ai import ai_fallback_dispatch as dispatch
from declan.ai.openai_planner import NonBillablePlanningError


class FailureReasonTests(unittest.TestCase):
    def test_specific_replies(self):
        cases = (
            (NonBillablePlanningError("OpenAI plan request rejected (HTTP 401)"), "rejected the API key"),
            (NonBillablePlanningError("OpenAI plan request rejected (HTTP 404)"), "isn't available on your OpenAI account"),
            (NonBillablePlanningError("OpenAI plan request rejected (HTTP 429)"), "rate limiting"),
            (NonBillablePlanningError("OpenAI plan request rejected (HTTP 400)"), "OpenAI rejected the request."),
            (ValueError("OpenAI plan request failed (HTTP 502)"), "server problem"),
            (ValueError("OpenAI plan request unavailable"), "couldn't reach OpenAI"),
            (ValueError("Invalid model plan"), "didn't pass my safety checks"),
            (ValueError("Action not permitted"), "didn't pass my safety checks"),
            (ValueError("Entity not currently available"), "unavailable in Home Assistant"),
            (ValueError("Missing capability attributes"), "can't be controlled safely"),
            (NonBillablePlanningError("OpenAI API key is not configured"), "isn't set up yet"),
            (NonBillablePlanningError("AI request context exceeds spending ceiling"), "per-request maximum"),
            (sqlite3.OperationalError("disk I/O"), "couldn't safely complete"),
            (ValueError("something new"), "couldn't safely complete"),
        )
        for error, expected in cases:
            with self.subTest(error=str(error)):
                reply = dispatch.explain_failure(error)
                self.assertIn(expected, reply)
                self.assertTrue(reply.endswith("No devices were changed."))

    def test_reason_is_short_and_logged_text_has_no_database_detail(self):
        self.assertEqual(dispatch.explain_reason(sqlite3.OperationalError("/opt/declan/.data x")), "local database error")
        self.assertLessEqual(len(dispatch.explain_reason(ValueError("x" * 500))), 160)

    def test_http_code_reaches_the_error(self):
        source = (dispatch.__file__.replace("ai_fallback_dispatch.py", "openai_planner.py"))
        with open(source, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn('f"OpenAI plan request rejected (HTTP {error.code})"', text)


if __name__ == "__main__":
    unittest.main()
