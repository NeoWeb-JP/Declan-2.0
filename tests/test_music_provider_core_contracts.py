"""Validate music provider results before they leave legacy public APIs."""
from email.message import Message
import unittest
import io
import json
from urllib.error import HTTPError
from unittest.mock import patch, Mock

from declan.music import music
from declan.core.execution_results import ExecutionResult, Outcome
from declan.music.music_provider_result import PlayerAvailability
from declan.music.music_provider_result import MusicFailureKind, MusicRequestFailure
from result_pairs import pair_of


class MusicProviderCoreContractTests(unittest.TestCase):
    def test_request_failures_are_typed_and_project_only_safe_diagnostics(self):
        for code, expected in ((429, MusicFailureKind.RATE_LIMITED), (502, MusicFailureKind.SERVICE_UNAVAILABLE),
                               (503, MusicFailureKind.SERVICE_UNAVAILABLE), (504, MusicFailureKind.SERVICE_UNAVAILABLE),
                               (400, MusicFailureKind.HTTP_ERROR), (401, MusicFailureKind.HTTP_ERROR),
                               (500, MusicFailureKind.HTTP_ERROR)):
            with self.subTest(code=code):
                failure = MusicRequestFailure.from_http_status(code)
                self.assertIs(failure.kind, expected)
                self.assertEqual(failure.http_status, code)
                with self.assertRaises(AttributeError):
                    setattr(failure, "kind", MusicFailureKind.TIMEOUT)
                error = HTTPError("http://private.invalid/?token=secret", code, "secret provider message", Message(), io.BytesIO())
                with patch.object(music, "_request", side_effect=error) as request, patch.object(music.diagnostics, "persist"):
                    with music.diagnostics.request("/api/assist") as trace:
                        with self.assertRaises(HTTPError) as raised:
                            music.request(None, "/api/services/media_player/play_media", {"entity_id": "media_player.kitchen"})
                self.assertIs(raised.exception, error)
                request.assert_called_once()
                stage = trace["stages"][0]
                self.assertEqual(stage["failure_kind"], expected.value)
                self.assertIs(type(stage["failure_kind"]), str)
                self.assertEqual(stage["http_status"], code)
                self.assertEqual(stage["outcome"], "failed")
                self.assertNotIn("secret", json.dumps(trace))
                error.close()

    def test_timeout_diagnostic_preserves_exception_and_never_retries(self):
        error = TimeoutError("secret timeout")
        with patch.object(music, "_request", side_effect=error) as request, patch.object(music.diagnostics, "persist"):
            with music.diagnostics.request("/api/assist") as trace:
                with self.assertRaises(TimeoutError) as raised:
                    music.request(None, "/api/services/media_player/media_pause", {"entity_id": "media_player.kitchen"})
        self.assertIs(raised.exception, error)
        request.assert_called_once()
        self.assertEqual(trace["stages"][0]["failure_kind"], "timeout")
        self.assertNotIn("secret", json.dumps(trace))

    def test_player_availability_is_typed_frozen_and_preserves_boolean_api(self):
        for state in (None, "unknown", "unavailable", "playing", "paused", "idle", "off", "future_state", ""):
            with self.subTest(state=state):
                expected = state not in (None, "unknown", "unavailable")
                result = music.player_availability_result("media_player.kitchen", state)
                self.assertIs(result.status, PlayerAvailability.AVAILABLE if expected else PlayerAvailability.UNAVAILABLE)
                self.assertIs(result.available, expected)
                self.assertIs(music.player_available("media_player.kitchen", state), expected)
                with self.assertRaises(AttributeError):
                    setattr(result, "status", PlayerAvailability.AVAILABLE)

    def test_feedback_public_api_preserves_legacy_tuple(self):
        with patch.object(music, "_feedback_provider", return_value=("Saved", "music_feedback")):
            self.assertEqual(pair_of(music.feedback_result)(("like", None), "ha", Mock()),
                             ("Saved", "music_feedback"))

    def test_control_public_api_preserves_kwargs(self):
        with patch.object(music, "_control_provider", return_value=("Stopped", "confirmed")) as core:
            self.assertEqual(pair_of(music.control_result)(("media_stop", None), "ha", Mock(),
                                           origin="kitchen", assist=True),
                             ("Stopped", "confirmed"))
            self.assertEqual(core.call_args.kwargs["origin"], "kitchen")
            self.assertTrue(core.call_args.kwargs["assist"])

    def test_play_public_api_preserves_origin(self):
        with patch.object(music, "_play_provider", return_value=("Playing", "confirmed")) as core:
            self.assertEqual(pair_of(music.play_result)(("kitchen", "country", "spotify"), "ha", Mock(),
                                        origin="satellite"), ("Playing", "confirmed"))
            self.assertEqual(core.call_args.kwargs["origin"], "satellite")

    def test_legacy_api_accepts_typed_core_result(self):
        with patch.object(music, "_play_provider",
                          return_value=ExecutionResult("Playing", Outcome.CONFIRMED)):
            self.assertEqual(pair_of(music.play_result)(("kitchen", "country", "spotify"), "ha", Mock()),
                             ("Playing", "confirmed"))

    def test_invalid_provider_outcomes_fail_closed(self):
        for name, provider, args in (
            ("feedback_result", "_feedback_provider", (("like", None), "ha", Mock())),
            ("control_result", "_control_provider", (("media_stop", None), "ha", Mock())),
            ("play_result", "_play_provider", (("kitchen", "country", "spotify"), "ha", Mock())),
        ):
            with self.subTest(name=name), patch.object(music, provider,
                                                        return_value=("Done", "unknown")):
                with self.assertRaises(ValueError):
                    getattr(music, name)(*args)

    def test_unverified_is_not_upgraded_to_confirmed(self):
        with patch.object(music, "_control_provider",
                          return_value=("Could not verify", "unverified")):
            self.assertEqual(pair_of(music.control_result)(("media_stop", None), "ha", Mock())[1],
                             "unverified")


if __name__ == "__main__":
    unittest.main()
