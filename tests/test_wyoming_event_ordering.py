"""Wyoming event ordering regressions without a Home Assistant installation."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / "custom_components"
          / "declan_two" / "wyoming_speaker_stt.py").read_text()
MODULE = ast.parse(SOURCE)
RECEIVE = next(node for node in MODULE.body
               if isinstance(node, ast.AsyncFunctionDef) and node.name == "receive")


class Event:
    def __init__(self, kind, data=None):
        self.type = kind
        self.data = data or {}


class Client:
    def __init__(self, events):
        self.events = iter(events)

    async def read_event(self):
        return next(self.events, None)


class Transcript:
    @staticmethod
    def is_type(kind):
        return kind == "transcript"

    @staticmethod
    def from_event(event):
        return SimpleNamespace(text=event.data["text"])


class Error:
    @staticmethod
    def is_type(kind):
        return kind == "error"


class State:
    SUCCESS = "success"
    ERROR = "error"


def speech_result(text, state):
    return SimpleNamespace(text=text, result=state)


def valid_speaker(identity_id, name, confidence):
    return bool(identity_id and str(identity_id).strip()) and (
        isinstance(name, str) and name.strip().casefold()
        not in ("", "unknown", "unidentified", "none")
    ) and isinstance(confidence, float) and 0 <= confidence <= 1


namespace = {
    "asyncio": asyncio,
    "Transcript": Transcript,
    "Error": Error,
    "stt": SimpleNamespace(SpeechResult=speech_result, SpeechResultState=State),
    "valid_wyoming_speaker": valid_speaker,
    "SpeakerMetadata": lambda speaker, capture: SimpleNamespace(speaker=speaker),
    "transcript_for_ha": lambda text, metadata: SimpleNamespace(
        text=text, speaker=metadata.speaker),
    "_LOGGER": SimpleNamespace(info=lambda *args: None),
}
exec(compile(ast.Module(body=[RECEIVE], type_ignores=[]), "<wyoming-receive>", "exec"), namespace)
receive = namespace["receive"]


def speaker(name, identity="id-1"):
    return Event("jarvis-speaker", {
        "speaker": name, "interaction_id": identity, "confidence": 0.9,
    })


class WyomingOrderingTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_before_transcript_then_valid_identity(self):
        result = await receive(Client([
            speaker("unknown"), Event("transcript", {"text": "lights on"}),
            speaker("Jaco"),
        ]))
        self.assertEqual(result.result, State.SUCCESS)
        self.assertEqual(result.text.speaker, ("id-1", "Jaco", 0.9))

    async def test_transcript_then_unknown_then_valid_identity(self):
        result = await receive(Client([
            Event("transcript", {"text": "lights on"}),
            speaker("unidentified"), speaker("Edd"),
        ]))
        self.assertEqual(result.text.speaker, ("id-1", "Edd", 0.9))

    async def test_repeated_unknown_events_do_not_extend_deadline(self):
        class RepeatingUnknownClient:
            async def read_event(self):
                await asyncio.sleep(0.06)
                return speaker("unknown")

        class FirstTranscriptClient:
            def __init__(self):
                self.first = True
                self.repeating = RepeatingUnknownClient()

            async def read_event(self):
                if self.first:
                    self.first = False
                    return Event("transcript", {"text": "lights on"})
                return await self.repeating.read_event()

        start = asyncio.get_running_loop().time()
        result = await asyncio.wait_for(receive(FirstTranscriptClient()), timeout=1)
        elapsed = asyncio.get_running_loop().time() - start
        self.assertEqual(result.result, State.SUCCESS)
        self.assertIsNone(result.text.speaker)
        self.assertLess(elapsed, 0.8)

    async def test_blank_transcripts_are_not_successful_commands(self):
        for text in ("", "   ", "\t"):
            with self.subTest(text=text):
                result = await receive(Client([
                    speaker("Jaco"), Event("transcript", {"text": text}),
                ]))
                self.assertEqual(result.result, State.ERROR)
                self.assertIsNone(result.text)

    async def test_valid_transcript_still_succeeds(self):
        result = await receive(Client([
            speaker("Jaco"), Event("transcript", {"text": "lights on"}),
        ]))
        self.assertEqual(result.result, State.SUCCESS)
        self.assertEqual(result.text.text, "lights on")

    async def test_duplicate_transcript_does_not_replace_first_command(self):
        result = await receive(Client([
            Event("transcript", {"text": "turn on lounge light"}),
            Event("transcript", {"text": "turn off all lights"}),
            speaker("Jaco"),
        ]))
        self.assertEqual(result.result, State.SUCCESS)
        self.assertEqual(result.text.text, "turn on lounge light")
        self.assertEqual(result.text.speaker, ("id-1", "Jaco", 0.9))

    async def test_blank_duplicate_does_not_discard_valid_transcript(self):
        result = await receive(Client([
            Event("transcript", {"text": "lights on"}),
            Event("transcript", {"text": " "}),
            speaker("Jaco"),
        ]))
        self.assertEqual(result.result, State.SUCCESS)
        self.assertEqual(result.text.text, "lights on")

    async def test_unknown_only_remains_anonymous(self):
        result = await receive(Client([
            speaker("none"), Event("transcript", {"text": "lights on"}),
        ]))
        self.assertEqual(result.result, State.SUCCESS)
        self.assertIsNone(result.text.speaker)


if __name__ == "__main__":
    unittest.main()
