"""Keep documented runtime environment settings aligned with backend reads."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
BACKEND_MODULES = (
    "server.py", "configuration.py", "music.py", "voicepipeline.py",
    "updates.py", "sensitive_confirmations.py", "declan_logs.py",
    "command_responses.py", "routine_responses.py", "script_discovery.py",
    "personality.py", "response_library.py", "arbitration.py",
)
ENV_READ = re.compile(
    r"""(?:\bos\.getenv|\bgetenv|\bos\.environ\.get|\benviron\.get)\s*\(\s*['"](DECLAN_[A-Z0-9_]+)['"]"""
)
DOCUMENTED = re.compile(r"`(DECLAN_[A-Z0-9_]+)`")


class EnvironmentDocumentationTests(unittest.TestCase):
    def test_backend_environment_reads_are_documented(self):
        documented = set(DOCUMENTED.findall((ROOT / "docs/environment.md").read_text(encoding="utf-8")))
        missing = {}
        for filename in BACKEND_MODULES:
            source = (ROOT / filename).read_text(encoding="utf-8")
            undocumented = sorted(set(ENV_READ.findall(source)) - documented)
            if undocumented:
                missing[filename] = undocumented
        self.assertEqual(missing, {}, "Document runtime environment reads in docs/environment.md")

    def test_example_environment_keys_are_documented(self):
        documented = set(DOCUMENTED.findall((ROOT / "docs/environment.md").read_text(encoding="utf-8")))
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        example_keys = set(re.findall(r"^\s*#?\s*(DECLAN_[A-Z0-9_]+)\s*=", example, re.MULTILINE))
        self.assertEqual(sorted(example_keys - documented), [], "Document .env.example keys")


if __name__ == "__main__":
    unittest.main()
