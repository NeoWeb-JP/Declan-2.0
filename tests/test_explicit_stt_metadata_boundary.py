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

    def test_missing_capture_is_preserved(self):
        transcript = MODULE.transcript_for_ha(
            "hello", MODULE.SpeakerMetadata(None, None),
        )
        self.assertIsNone(transcript.capture_level)
        self.assertEqual(MODULE.speaker_request_payload(transcript),
                         {"speaker": {}})


if __name__ == "__main__":
    unittest.main()
