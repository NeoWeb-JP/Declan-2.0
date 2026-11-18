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
