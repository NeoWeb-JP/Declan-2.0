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
    "history.py", "timers.py", "conditions.py", "web_stt.py",
    "diagnostics.py", "voice_profiles.py", "lighting_intents.py",
    "custom_components/declan_two/conversation.py",
    "custom_components/declan_two/stt.py",
    "custom_components/declan_two/tts.py",
    "custom_components/declan_two/voice_defaults.py",
    "custom_components/declan_two/routine_jobs.py",
    "custom_components/declan_two/updates_view.py",
    "custom_components/declan_two/management_view.py",
    "custom_components/declan_two/microphone_view.py",
    "custom_components/declan_two/ha_audit_view.py",
    "custom_components/declan_two/__init__.py",
    "custom_components/declan_two/history_view.py",
    "custom_components/declan_two/chat_view.py",
    "custom_components/declan_two/media_players_view.py",
    "custom_components/declan_two/music_playlists_view.py",
    "custom_components/declan_two/ai_settings_view.py",
    "custom_components/declan_two/voice_review_view.py",
    "custom_components/declan_two/settings_status_view.py",
    "custom_components/declan_two/script_discovery_view.py",
    "custom_components/declan_two/script_result_view.py",
    "custom_components/declan_two/capabilities_view.py",
    "custom_components/declan_two/config_flow.py",
    "approved_media_players.py",
    "openai_planner.py",
    "spotify_playlists.py",
)
ENV_READ = re.compile(
    r"""(?:\b(?:os\.)?getenv\s*\(\s*|\b(?:os\.)?environ(?:\.get\s*\(\s*|\[\s*))['"](DECLAN_[A-Z0-9_]+)['"]"""
)
DOCUMENTED = re.compile(r"^\|\s*\`(DECLAN_[A-Z0-9_]+)\`\s*\|", re.MULTILINE)


class EnvironmentDocumentationTests(unittest.TestCase):
    def test_detects_supported_environment_read_forms(self):
        examples = (
            'os.getenv("DECLAN_EXAMPLE")',
            'getenv("DECLAN_EXAMPLE")',
            'os.environ.get("DECLAN_EXAMPLE", "default")',
            'environ.get("DECLAN_EXAMPLE")',
            'os.environ["DECLAN_EXAMPLE"]',
            'environ["DECLAN_EXAMPLE"]',
        )
        for expression in examples:
            with self.subTest(expression=expression):
                self.assertEqual(ENV_READ.findall(expression), ["DECLAN_EXAMPLE"])

    def test_backend_environment_reads_are_documented(self):
        documented = set(DOCUMENTED.findall((ROOT / "docs/environment.md").read_text(encoding="utf-8")))
        missing = {}
        for filename in BACKEND_MODULES:
            source = (ROOT / filename).read_text(encoding="utf-8")
            undocumented = sorted(set(ENV_READ.findall(source)) - documented)
            if undocumented:
                missing[filename] = undocumented
        self.assertEqual(missing, {}, "Document runtime environment reads in docs/environment.md")

    def test_audit_scope_includes_all_modules_reading_documented_environment_keys(self):
        """Flag newly added modules with environment reads for audit expansion."""
        scoped = set(BACKEND_MODULES)
        candidates = sorted(
            file for file in ROOT.rglob("*.py")
            if not any(part in {"tests", ".git", ".venv", "venv", "node_modules"}
                       for part in file.relative_to(ROOT).parts)
        )
        unaudited = {}
        for file in candidates:
            relative = file.relative_to(ROOT).as_posix()
            if relative in scoped:
                continue
            keys = sorted(set(ENV_READ.findall(file.read_text(encoding="utf-8"))))
            if keys:
                unaudited[relative] = keys
        self.assertEqual(
            unaudited, {},
            "Add modules with runtime DECLAN_* reads to BACKEND_MODULES and document new keys",
        )

    def test_environment_inventory_has_unique_described_entries(self):
        """Each environment setting needs one meaningful purpose and example."""
        inventory = (ROOT / "docs/environment.md").read_text(encoding="utf-8")
        entries = []
        incomplete = []
        for line in inventory.splitlines():
            if not DOCUMENTED.match(line):
                continue
            columns = [column.strip() for column in line.strip().strip("|").split("|")]
            key = DOCUMENTED.match(line).group(1)
            entries.append(key)
            if len(columns) < 3 or not columns[1] or not columns[2]:
                incomplete.append(key)
        self.assertEqual(incomplete, [], "Document a purpose and example for each setting")
        duplicates = sorted({key for key in entries if entries.count(key) > 1})
        self.assertEqual(duplicates, [], "Each environment setting needs one inventory row")

    def test_example_environment_keys_are_documented(self):
        documented = set(DOCUMENTED.findall((ROOT / "docs/environment.md").read_text(encoding="utf-8")))
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        example_keys = set(re.findall(r"^\s*#?\s*(DECLAN_[A-Z0-9_]+)\s*=", example, re.MULTILINE))
        self.assertEqual(sorted(example_keys - documented), [], "Document .env.example keys")


if __name__ == "__main__":
    unittest.main()
