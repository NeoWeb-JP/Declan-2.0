"""Speaker transcript compatibility and metadata loss regressions."""
import importlib.util
from pathlib import Path
import pickle
import sys
import unittest


MODULE_PATH = (Path(__file__).resolve().parents[1] /
               "custom_components/declan_two/speaker_models.py")
SPEC = importlib.util.spec_from_file_location("speaker_models_under_test", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load speaker transcript module")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
SpeakerTranscript = MODULE.SpeakerTranscript


class SpeakerTranscriptTests(unittest.TestCase):
    def test_canonical_and_legacy_speaker_aliases(self):
        transcript = SpeakerTranscript("Hello", speaker="Edd",
                                       capture_level={"confidence": 0.95})
        self.assertEqual(transcript.speaker, "Edd")
        self.assertEqual(transcript.jarvis_speaker, "Edd")
        transcript.jarvis_speaker = "Jaco"
        self.assertEqual(transcript.speaker, "Jaco")
        self.assertEqual(str(transcript), "Hello")

    def test_pickle_round_trip_retains_metadata(self):
        transcript = SpeakerTranscript("Turn on the light", "Jaco",
                                       {"confidence": 0.93})
        restored = pickle.loads(pickle.dumps(transcript))
        self.assertEqual(restored, transcript)
        self.assertEqual(restored.speaker, "Jaco")
        self.assertEqual(restored.jarvis_speaker, "Jaco")
        self.assertEqual(restored.capture_level, {"confidence": 0.93})

    def test_string_operations_do_not_preserve_identity(self):
        transcript = SpeakerTranscript("HELLO", "Jaco")
        transformed = transcript.lower()
        self.assertEqual(transformed, "hello")
        self.assertNotIsInstance(transformed, SpeakerTranscript)
        self.assertFalse(hasattr(transformed, "speaker"))

    def test_canonical_speaker_is_preferred_for_fallback(self):
        self.assertEqual(MODULE.speaker_from_transcript(
            SpeakerTranscript("hello", speaker="speaker-1")), "speaker-1")

    def test_legacy_only_speaker_is_supported(self):
        class LegacyTranscript(str):
            jarvis_speaker = "speaker-2"
        self.assertEqual(MODULE.speaker_from_transcript(
            LegacyTranscript("hello")), "speaker-2")

    def test_metadata_snapshot_survives_transcript_normalization(self):
        original = SpeakerTranscript("HELLO", "speaker-1", {"confidence": 0.9})
        metadata = MODULE.metadata_from_transcript(original)
        normalized = original.lower()
        self.assertEqual(normalized, "hello")
        self.assertFalse(hasattr(normalized, "speaker"))
        self.assertEqual(metadata.speaker, "speaker-1")
        self.assertEqual(metadata.capture_level, {"confidence": 0.9})

    def test_capture_snapshot_is_independent_of_transcript_mutations(self):
        capture = {"confidence": 0.9}
        transcript = SpeakerTranscript("HELLO", "speaker-1", capture)
        snapshot = MODULE.metadata_from_transcript(transcript)
        capture["confidence"] = 0.2
        transcript.capture_level = {"confidence": 0.1}
        self.assertEqual(snapshot.capture_level, {"confidence": 0.9})
        self.assertEqual(snapshot.speaker, "speaker-1")

    def test_capture_snapshot_is_independent_of_caller_mutations(self):
        transcript = SpeakerTranscript("HELLO", "speaker-1", {"confidence": 0.9})
        snapshot = MODULE.metadata_from_transcript(transcript)
        snapshot.capture_level["confidence"] = 0.2
        self.assertEqual(transcript.capture_level, {"confidence": 0.9})

    def test_malformed_capture_metadata_does_not_break_speaker_extraction(self):
        for invalid in ("not-a-mapping", 7, ["unexpected"], object()):
            with self.subTest(value=type(invalid).__name__):
                transcript = SpeakerTranscript("hello", ("id", "Jaco", 0.9), invalid)
                metadata = MODULE.metadata_from_transcript(transcript)
                self.assertIsNone(metadata.capture_level)
                self.assertEqual(metadata.speaker, ("id", "Jaco", 0.9))
                self.assertEqual(MODULE.speaker_request_payload(transcript), {
                    "speaker": {"interaction_id": "id", "name": "Jaco",
                                "confidence": 0.9},
                })

    def test_metadata_snapshot_retains_structured_identity(self):
        identity = ("interaction-42", "Edd", 0.87)
        transcript = SpeakerTranscript("hello", identity, {"rms": 0.1})
        metadata = MODULE.metadata_from_transcript(transcript)
        self.assertEqual(metadata.speaker, identity)
        self.assertEqual(metadata.capture_level, {"rms": 0.1})
        self.assertEqual(MODULE.speaker_request_payload(transcript)["speaker"], {
            "interaction_id": "interaction-42", "name": "Edd",
            "confidence": 0.87,
        })

    def test_metadata_snapshot_preserves_legacy_string_identity(self):
        transcript = SpeakerTranscript("hello", "Jaco")
        self.assertEqual(MODULE.metadata_from_transcript(transcript).speaker, "Jaco")

    def test_legacy_metadata_snapshot(self):
        class LegacyTranscript(str):
            jarvis_speaker = "speaker-2"
        metadata = MODULE.metadata_from_transcript(LegacyTranscript("hello"))
        self.assertEqual(metadata.speaker, "speaker-2")
        self.assertIsNone(metadata.capture_level)

    def test_assist_payload_preserves_valid_speaker_and_capture(self):
        transcript = SpeakerTranscript("hello", ("id-1", "Jaco", 0.95),
                                       {"confidence": 0.8})
        payload = MODULE.speaker_request_payload(transcript)
        self.assertEqual(payload, {
            "speaker": {"interaction_id": "id-1", "name": "Jaco",
                        "confidence": 0.95},
            "capture": {"confidence": 0.8},
        })
        transcript.capture_level["confidence"] = 0.1
        self.assertEqual(payload["capture"]["confidence"], 0.8)

    def test_assist_payload_keeps_legacy_empty_speaker(self):
        self.assertEqual(MODULE.speaker_request_payload(
            SpeakerTranscript("hello")), {"speaker": {}})

    def test_assist_payload_omits_invalid_speaker_tuple(self):
        self.assertEqual(MODULE.speaker_request_payload(
            SpeakerTranscript("hello", ("id", "Jaco", 2.0))), {})

    def test_assist_payload_accepts_legacy_only_speaker(self):
        class LegacyTranscript(str):
            jarvis_speaker = ("interaction-2", "Edd", 0.91)
        self.assertEqual(MODULE.speaker_request_payload(LegacyTranscript("hello")), {
            "speaker": {"interaction_id": "interaction-2",
                        "name": "Edd", "confidence": 0.91},
        })

    def test_assist_payload_rejects_boolean_confidence(self):
        self.assertEqual(MODULE.speaker_request_payload(
            SpeakerTranscript("hello", ("id", "Jaco", True))), {})

    def test_assist_payload_rejects_invalid_tuple_fields(self):
        for speaker in ((12, "Jaco", 0.8), ("id", None, 0.8),
                        ("id", "Jaco", -0.1), ("id", "Jaco", 1.1)):
            with self.subTest(speaker=speaker):
                self.assertEqual(MODULE.speaker_request_payload(
                    SpeakerTranscript("hello", speaker)), {})

    def test_assist_payload_preserves_capture_without_speaker(self):
        transcript = SpeakerTranscript("hello", capture_level={"confidence": 0.7})
        self.assertEqual(MODULE.speaker_request_payload(transcript), {
            "speaker": {}, "capture": {"confidence": 0.7},
        })

    def test_assist_payload_filters_non_json_capture_values(self):
        transcript = SpeakerTranscript("hello", ("id", "Jaco", 0.9), {
            "duration": 1.5, "rms": float("nan"), "object": object(),
            "bad": float("inf"), "negative": -1, "valid": 0.0,
        })
        self.assertEqual(MODULE.speaker_request_payload(transcript), {
            "speaker": {"interaction_id": "id", "name": "Jaco",
                        "confidence": 0.9},
            "capture": {"duration": 1.5, "valid": 0.0},
        })

    def test_assist_payload_omits_entirely_invalid_capture(self):
        transcript = SpeakerTranscript("hello", capture_level={"value": object()})
        self.assertEqual(MODULE.speaker_request_payload(transcript), {"speaker": {}})

    def test_assist_payload_plain_text_is_empty(self):
        self.assertEqual(MODULE.speaker_request_payload("hello"), {})

    def test_plain_transcript_has_no_identity(self):
        self.assertIsNone(MODULE.speaker_from_transcript("hello"))

    def test_canonical_identity_wins_over_stale_legacy(self):
        class MixedTranscript(str):
            speaker = "speaker-3"
            jarvis_speaker = "old-speaker"
        self.assertEqual(MODULE.speaker_from_transcript(
            MixedTranscript("hello")), "speaker-3")


if __name__ == "__main__":
    unittest.main()
