"""Regression coverage for explicit STT metadata at the HA compatibility edge."""
import importlib.util
from pathlib import Path
import sys
import unittest


MODULE_PATH = (Path(__file__).resolve().parents[1] / "custom_components"
               / "declan_two" / "speaker_models.py")
SPEC = importlib.util.spec_from_file_location("explicit_speaker_models", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ExplicitSTTMetadataBoundaryTests(unittest.TestCase):
    def test_identity_and_capture_survive_compatibility_conversion(self):
        capture = {"duration": 1.5}
        metadata = MODULE.SpeakerMetadata(("id-1", "speaker", 0.8), capture)
        transcript = MODULE.transcript_for_ha("turn on the light", metadata)
        self.assertIsInstance(transcript, str)
        self.assertEqual(str(transcript), "turn on the light")
        self.assertEqual(MODULE.metadata_from_transcript(transcript), metadata)
        capture["duration"] = 3.0
        self.assertEqual(transcript.capture_level, {"duration": 1.5})

    def test_cloud_transcript_without_speaker_retains_capture(self):
        transcript = MODULE.transcript_for_ha(
            "hello", MODULE.SpeakerMetadata(None, {"rms": 0.2}),
        )
        self.assertEqual(MODULE.speaker_request_payload(transcript),
                         {"speaker": {}, "capture": {"rms": 0.2}})

    def test_wyoming_speaker_before_or_after_transcript_retains_identity(self):
        identity = ("interaction-42", "speaker", 0.93)
        first = MODULE.transcript_for_ha(
            "lights on", MODULE.SpeakerMetadata(identity, None),
        )
        final = MODULE.transcript_for_ha(
            first, MODULE.SpeakerMetadata(
                MODULE.metadata_from_transcript(first).speaker, {"peak": 0.75},
            ),
        )
        self.assertEqual(MODULE.speaker_request_payload(final), {
            "speaker": {"interaction_id": "interaction-42",
                        "name": "speaker", "confidence": 0.93},
            "capture": {"peak": 0.75},
        })

    def test_plain_text_has_no_speaker_or_capture_payload(self):
        metadata = MODULE.metadata_from_transcript("hello")
        self.assertEqual(
            MODULE.speaker_payload_from_metadata(metadata, speaker_present=False), {},
        )

    def test_legacy_speaker_attribute_is_snapshotted(self):
        class LegacyTranscript(str):
            jarvis_speaker = ("legacy-id", "speaker", 0.7)
            capture_level = {"peak": 0.4}

        transcript = LegacyTranscript("hello")
        metadata = MODULE.metadata_from_transcript(transcript)
        self.assertEqual(MODULE.speaker_payload_from_metadata(metadata, speaker_present=True), {
            "speaker": {"interaction_id": "legacy-id", "name": "speaker",
                        "confidence": 0.7},
            "capture": {"peak": 0.4},
        })

    def test_concurrent_request_snapshots_do_not_share_identity(self):
        first = MODULE.transcript_for_ha(
            "first", MODULE.SpeakerMetadata(("one", "J", 0.8), {"peak": 0.1}),
        )
        second = MODULE.transcript_for_ha(
            "second", MODULE.SpeakerMetadata(("two", "E", 0.9), {"peak": 0.9}),
        )
        first_payload = MODULE.snapshot_speaker_payload(first)
        second_payload = MODULE.snapshot_speaker_payload(second)
        self.assertEqual(first_payload["speaker"]["interaction_id"], "one")
        self.assertEqual(second_payload["speaker"]["interaction_id"], "two")
        self.assertEqual(MODULE.snapshot_speaker_payload("typed request"), {})
        first_payload["capture"]["peak"] = 0.5
        self.assertEqual(second_payload["capture"]["peak"], 0.9)
        self.assertEqual(MODULE.snapshot_speaker_payload(first)["capture"]["peak"], 0.1)

    def test_malformed_identity_does_not_enter_assist_payload(self):
        for identity in [("", "speaker", 0.8), ("id", "", 0.8),
                         ("x" * 81, "speaker", 0.8),
                         ("id", "x" * 81, 0.8), ("id", "speaker", True),
                         ("id", "speaker", float("nan"))]:
            with self.subTest(identity=identity):
                transcript = MODULE.transcript_for_ha(
                    "hello", MODULE.SpeakerMetadata(identity, {"peak": 0.3}),
                )
                self.assertEqual(MODULE.snapshot_speaker_payload(transcript),
                                 {"capture": {"peak": 0.3}})

    def test_invalid_capture_values_are_excluded(self):
        transcript = MODULE.transcript_for_ha(
            "hello", MODULE.SpeakerMetadata(None, {
                "peak": 0.5, "boolean": True, "negative": -1,
                "nan": float("nan"), "": 0.1,
            }),
        )
        self.assertEqual(MODULE.snapshot_speaker_payload(transcript), {
            "speaker": {}, "capture": {"peak": 0.5},
        })

    def test_missing_capture_is_preserved(self):
        transcript = MODULE.transcript_for_ha(
            "hello", MODULE.SpeakerMetadata(None, None),
        )
        self.assertIsNone(transcript.capture_level)
        self.assertEqual(MODULE.speaker_request_payload(transcript),
                         {"speaker": {}})


if __name__ == "__main__":
    unittest.main()
