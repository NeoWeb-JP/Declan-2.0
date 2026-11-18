"""Release updater must refuse activation without the voice encryption runtime."""
import ast
import unittest
from pathlib import Path


class VoiceCryptoReleasePreflightTests(unittest.TestCase):
    def test_dependency_preflight_precedes_activation_and_snapshot(self):
        source = (Path(__file__).resolve().parents[1] / 'updates.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        install = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'install')
        lines = source.splitlines()
        guard = next(node for node in ast.walk(install) if isinstance(node, ast.If)
                     and 'voice_audio_crypto.py' in ast.get_source_segment(source, node.test))
        guard_text = '\\n'.join(lines[guard.lineno - 1:guard.end_lineno])
        self.assertIn('cryptography.hazmat.primitives.ciphers.aead', guard_text)
        self.assertLess(guard.lineno, source.index('state_backup.snapshot(APP / ".data")') // 1 + 1)
        self.assertLess(guard.lineno, next(node.lineno for node in ast.walk(install)
                                         if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                                         and node.func.attr == 'symlink_to'))


if __name__ == '__main__':
    unittest.main()
