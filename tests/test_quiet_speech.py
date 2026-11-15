"""Quiet speech tests: never alter source media-player volume."""
import unittest
import wave
from datetime import datetime
from io import BytesIO
from array import array

from custom_components.declan_two.quiet_speech import attenuate_wav, quiet_hours


def wav(values):
    result = BytesIO()
    with wave.open(result, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(array("h", values).tobytes())
    return result.getvalue()


def samples(audio):
    with wave.open(BytesIO(audio), "rb") as source:
        values = array("h")
        values.frombytes(source.readframes(source.getnframes()))
        return list(values)


class QuietSpeechTests(unittest.TestCase):
    def test_quiet_window(self):
        self.assertTrue(quiet_hours(datetime(2026, 11, 15, 23)))
        self.assertTrue(quiet_hours(datetime(2026, 11, 15, 6, 59)))
        self.assertFalse(quiet_hours(datetime(2026, 11, 15, 7)))

    def test_night_reduces_pcm_to_twenty_percent(self):
        original = wav([10000, -10000, 2000])
        night = attenuate_wav(original, now=datetime(2026, 11, 15, 23))
        self.assertEqual(samples(night), [2000, -2000, 400])
        self.assertEqual(samples(original), [10000, -10000, 2000])

    def test_day_preserves_original_audio(self):
        original = wav([10000, -10000])
        self.assertIs(attenuate_wav(original, now=datetime(2026, 11, 15, 12)), original)


if __name__ == "__main__":
    unittest.main()
