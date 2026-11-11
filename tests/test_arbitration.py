"""Competing satellite captures choose one executor without fixed device maps."""

from concurrent.futures import ThreadPoolExecutor
from time import time
from unittest import TestCase

from arbitration import CaptureArbiter
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_spec = spec_from_file_location("declan_capture_level", Path(__file__).resolve().parents[1] / "custom_components/declan_two/capture_level.py")
_capture = module_from_spec(_spec)
_spec.loader.exec_module(_capture)
CaptureLevel = _capture.CaptureLevel


class ArbitrationTests(TestCase):
    def test_overlapping_captures_choose_one_executor_and_reject_late_duplicate(self):
        arbiter = CaptureArbiter(window=0.03)
        end = time()
        with ThreadPoolExecutor(max_workers=2) as pool:
            quiet = pool.submit(arbiter.claim, "dinner time", "satellite.kitchen", {"ended_at": end, "duration": 2, "rms": 0.1})
            loud = pool.submit(arbiter.claim, "dinner time", "satellite.bedroom", {"ended_at": end, "duration": 2, "rms": 0.5})
            self.assertEqual(sorted((quiet.result(), loud.result())), [False, True])
        self.assertFalse(arbiter.claim("dinner time", "satellite.hall", {"ended_at": end, "duration": 2, "rms": 0.9}))
        self.assertTrue(arbiter.claim("dinner time", "satellite.hall", {"ended_at": end + 3, "duration": 1, "rms": 0.9}))

    def test_distinct_speakers_commands_and_missing_metadata_are_not_suppressed(self):
        arbiter = CaptureArbiter(window=0)
        capture = {"ended_at": time(), "duration": 2, "rms": 0.5}
        self.assertTrue(arbiter.claim("hello", "kitchen", capture, "Jaco"))
        self.assertTrue(arbiter.claim("hello", "bedroom", capture, "Edd"))
        self.assertTrue(arbiter.claim("bye", "hall", capture))
        self.assertFalse(arbiter.claim("hello", "kitchen", capture))
        self.assertTrue(arbiter.claim("hello", "kitchen", {**capture, "ended_at": capture["ended_at"] + 3}))
        self.assertTrue(arbiter.claim("hello", "hall", None))
        self.assertTrue(arbiter.claim("hello", "hall", {**capture, "rms": float("nan")}))

    def test_capture_measurement_preserves_split_pcm_samples(self):
        level = CaptureLevel()
        for part in (b"\x00", b"\x40\x00", b"\xc0"):
            level.add(part)
        self.assertIsNone(level.snapshot())
        level.finish()
        snapshot = level.snapshot()
        self.assertAlmostEqual(snapshot["rms"], 0.5)
        self.assertEqual(snapshot["duration"], 2 / 16000)
