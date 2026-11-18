"""Explicit speaker metadata projection and compatibility adapter tests."""
import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "declan_two" / "speaker_models.py"
spec = importlib.util.spec_from_file_location("declan_speaker_models_contract", MODULE_PATH)
models = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = models
spec.loader.exec_module(models)


class SpeakerMetadataBoundaryContractTests(unittest.TestCase):
    def test_explicit_metadata_survives_compatibility_adapter(self):
        metadata = models.SpeakerMetadata(
            ("interaction-1", "Jaco", 0.95), {"rms": 0.4})
        transcript = models.transcript_for_ha("Turn off the light", metadata)
        self.assertEqual(str(transcript), "Turn off the light")
        self.assertEqual(models.snapshot_speaker_payload(transcript), {
            "speaker": {"interaction_id": "interaction-1", "name": "Jaco",
                        "confidence": 0.95},
            "capture": {"rms": 0.4}})
        self.assertEqual(models.snapshot_speaker_payload(str(transcript).lower()), {})

    def test_capture_is_snapshotted_before_provider_mutation(self):
        capture = {"rms": 0.3}
        transcript = models.SpeakerTranscript("hello", capture_level=capture)
        snapshot = models.metadata_from_transcript(transcript)
        capture["rms"] = 0.9
        self.assertEqual(snapshot.capture_level, {"rms": 0.3})

    def test_hostile_string_subclasses_are_not_projected_as_speakers(self):
        class HostileText(str):
            def strip(self):
                raise RuntimeError("unexpected strip")
            def __hash__(self):
                raise RuntimeError("unexpected hash")
        for speaker in ((HostileText("id"), "Jaco", 0.9),
                        ("id", HostileText("Jaco"), 0.9)):
            with self.subTest(speaker=speaker[2]):
                payload = models.speaker_payload_from_metadata(
                    models.SpeakerMetadata(speaker, None))
                self.assertEqual(payload, {})

    def test_malformed_capture_keys_and_values_are_ignored(self):
        class HostileText(str):
            def __hash__(self):
                return str.__hash__(self)
        metadata = models.SpeakerMetadata(None, {
            "rms": 0.2, HostileText("bad"): 0.4,
            "boolean": True, "nan": float("nan"), "object": object()})
        self.assertEqual(models.speaker_payload_from_metadata(metadata),
                         {"capture": {"rms": 0.2}})

    def test_plain_transcript_has_no_speaker_identity(self):
        self.assertEqual(models.snapshot_speaker_payload("hello"), {})


if __name__ == "__main__":
    unittest.main()
