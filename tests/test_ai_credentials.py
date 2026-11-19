import tempfile
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from declan.ai import ai_credentials


class CredentialsTests(unittest.TestCase):
    def test_rejects_invalid_key(self):
        with self.assertRaises(ValueError):
            ai_credentials.replace_key("invalid")

    def test_secure_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "key"
            with patch.object(ai_credentials, "PATH", path):
                key = "sk-" + "a" * 30
                ai_credentials.replace_key(key)
                self.assertEqual(ai_credentials.get_key(), key)
                if os.name != "nt":
                    self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
