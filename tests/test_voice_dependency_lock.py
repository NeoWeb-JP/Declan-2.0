"""Dependency lock generator refuses incomplete downloads and never replaces live lock."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import generate_voice_dependency_lock as lock


class VoiceLockTests(unittest.TestCase):
    def test_candidate_contains_hashes_and_transitive_wheels(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'requirements-web-voice.txt'
            target.write_text('old lock\\n')
            def fake_run(args, **kwargs):
                folder = Path(args[args.index('--dest') + 1])
                for name in ('websocket_client-1.9.2-py3-none-any.whl',
                             'cryptography-46.0.3-cp312-abi3-manylinux.whl',
                             'cffi-2.0.0-cp312-abi3-manylinux.whl',
                             'pycparser-2.23-py3-none-any.whl'):
                    (folder / name).write_bytes(name.encode())
            candidate = lock.generate(target, runner=fake_run)
            text = candidate.read_text()
            for package in ('websocket-client==1.9.2', 'cryptography==46.0.3',
                            'cffi==2.0.0', 'pycparser==2.23'):
                self.assertIn(package + ' --hash=sha256:', text)
            self.assertEqual(target.read_text(), 'old lock\\n')
            self.assertIn(hashlib.sha256(b'pycparser-2.23-py3-none-any.whl').hexdigest(), text)

    def test_missing_required_wheel_does_not_write_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'requirements-web-voice.txt'
            def fake_run(args, **kwargs):
                folder = Path(args[args.index('--dest') + 1])
                (folder / 'websocket_client-1.9.2-py3-none-any.whl').write_bytes(b'wheel')
            with self.assertRaisesRegex(ValueError, 'Missing requested wheel'):
                lock.generate(target, runner=fake_run)
            self.assertFalse(target.with_name(target.name + '.candidate').exists())


if __name__ == '__main__':
    unittest.main()
