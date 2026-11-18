"""Regression guard for Wyoming upload task exception handling."""
import ast
from pathlib import Path
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / "custom_components"
          / "declan_two" / "wyoming_speaker_stt.py").read_text()
TREE = ast.parse(SOURCE)


class WyomingUploadFailureTests(unittest.TestCase):
    def test_upload_task_result_has_local_error_conversion(self):
        bridge = next(node for node in TREE.body
                      if isinstance(node, ast.ClassDef)
                      and node.name == "DeclanWyomingVoiceBridge")
        method = next(node for node in bridge.body
                      if isinstance(node, ast.AsyncFunctionDef)
                      and node.name == "async_process_audio_stream")
        result_calls = [
            node for node in ast.walk(method)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "upload_task"
            and node.func.attr == "result"
        ]
        self.assertEqual(len(result_calls), 1)
        call = result_calls[0]
        enclosing_handlers = [
            node for node in ast.walk(method)
            if isinstance(node, ast.Try)
            and any(child is call for statement in node.body
                    for child in ast.walk(statement))
        ]
        self.assertTrue(any(
            any(isinstance(handler.type, ast.Name)
                and handler.type.id == "Exception"
                and any(isinstance(item, ast.Return)
                        for statement in handler.body
                        for item in ast.walk(statement))
                for handler in candidate.handlers)
            for candidate in enclosing_handlers
        ), "Upload errors must return a normal STT error at the task boundary")


if __name__ == "__main__":
    unittest.main()
