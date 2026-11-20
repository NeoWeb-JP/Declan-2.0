"""Dependency lock generator refuses incomplete downloads and never replaces live lock."""
import hashlib
from pathlib import Path
import tempfile
import unittest

import generate_voice_dependency_lock as lock


class VoiceLockTests(unittest.TestCase):
    def test_candidate_contains_hashes_and_transitive_wheels(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'requirements-web-voice.txt'
            target.write_text('old lock\\n')
            def fake_run(args, **kwargs):
                folder = Path(args[args.index('--dest') + 1])
                for name in ('websocket_client-1.9.2-py3-none-any.whl',
                             'cryptography-50.0.0-cp312-abi3-manylinux.whl',
                             'cffi-2.0.0-cp312-abi3-manylinux.whl',
                             'pycparser-2.23-py3-none-any.whl'):
                    (folder / name).write_bytes(name.encode())
            candidate = lock.generate(target, runner=fake_run)
            text = candidate.read_text()
            self.assertEqual(len(text.splitlines()), 5)
            self.assertTrue(text.endswith(chr(10)))
            self.assertNotIn(chr(92) + 'n', text)
            for package in ('websocket-client==1.9.2', 'cryptography==50.0.0',
                            'cffi==2.0.0', 'pycparser==2.23'):
                self.assertIn(package + ' --hash=sha256:', text)
            self.assertEqual(target.read_text(), 'old lock\\n')
            self.assertIn(hashlib.sha256(b'pycparser-2.23-py3-none-any.whl').hexdigest(), text)

    def test_production_lock_covers_python_311_and_312_cffi_wheels(self):
        """cffi ships one wheel per Python version; the Proxmox host runs Python 3.11."""
        text = (Path(__file__).resolve().parents[1] / 'requirements-web-voice.txt').read_text()
        block = text.split('cffi==2.1.1', 1)[1].split('cryptography==', 1)[0]
        hashes = [part for part in block.replace(chr(92), ' ').split() if part.startswith('--hash=sha256:')]
        self.assertEqual(len(hashes), 2)
        # cp311 manylinux2014 x86_64 digest as published by PyPI and confirmed on the host.
        self.assertIn('--hash=sha256:34e261f78cb6ceaaa36f42f2613f4380d94d9c759a9c73c769ee6e0247364632', hashes)
        for line in text.splitlines():
            if line and not line.startswith(('#', ' ')) and '==' in line:
                self.assertTrue(line.endswith(chr(92)) or '--hash=sha256:' in line, line)

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
